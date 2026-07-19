#!/usr/bin/env python3
"""
LLaMA Server Launcher  —  pure tkinter/ttk
Fixed: Proper vertical scrolling, no phantom window, correct resizing.
Updated: Black background with white text.
New: Checkboxes to enable/disable sampling parameter flags.
Fixed: Token per second display (robust regex + debugging).
Fixed: MTP uses --spec-type draft-mtp and --spec-draft-n-max.
Fixed: --repeat-last-penalty → --repeat-last-n.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import subprocess, threading, json, os, re, sys, time
import urllib.request, urllib.error
from pathlib import Path
from datetime import datetime
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

# ── Optional: huggingface_hub for rich model card parsing ─────────
try:
    from huggingface_hub import ModelCard as HFModelCard
    HAS_HF_HUB = True
except ImportError:
    HAS_HF_HUB = False
    HFModelCard = None  # type: ignore[misc]

# ── Optional: yaml for front-matter parsing fallback ─────────────
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

# ── Colour palette (Black/White Theme) ─────────────────────
BG      = "#000000"  # Pure black background
BG2     = "#0a0a0a"  # Very dark gray
BG3     = "#141414"  # Dark gray (Entry fields)
BG4     = "#1e1e1e"  # Slightly lighter dark gray (Buttons)
FG      = "#ffffff"  # White text
FG2     = "#cccccc"  # Light gray (Secondary text)
ACCENT  = "#00ff88"  # Bright green accent
GREEN   = "#00ff88"  # Bright green
GREEN2  = "#00cc66"  # Darker green
RED     = "#ff4444"  # Bright red
RED2    = "#cc0000"  # Darker red
GOLD    = "#ffcc00"  # Gold/yellow
BLUE    = "#44aaff"  # Cyan/blue for capabilities
TEAL    = "#33ddbb"  # Teal for context/tokenizer
BORDER  = "#333333"  # Dark border

BOOTSTRAP_FILE = Path(__file__).parent / "llama_bootstrap.json"

def _atomic_write_json(path: Path, data) -> None:
    """Write JSON atomically: write to a temp file then rename, so a crash or
    power loss mid-write can't leave a half-written, unparseable file (which
    previously would silently reset to defaults on the next load with no
    indication anything had gone wrong)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(path)

def _load_bootstrap():
    try:
        if BOOTSTRAP_FILE.exists():
            d = json.loads(BOOTSTRAP_FILE.read_text()).get("config_dir", "")
            if d and Path(d).is_dir():
                return Path(d)
    except Exception as e:
        print(f"⚠ Could not read {BOOTSTRAP_FILE}: {e}", file=sys.stderr)
    return Path(__file__).parent

def _save_bootstrap(cfg_dir: Path):
    _atomic_write_json(BOOTSTRAP_FILE, {"config_dir": str(cfg_dir)})

_CFG_DIR = _load_bootstrap()
MODEL_CARDS_FILE = _CFG_DIR / "model_cards.json"

def _load_model_cards():
    try:
        if MODEL_CARDS_FILE.exists():
            return json.loads(MODEL_CARDS_FILE.read_text())
    except Exception as e:
        print(f"⚠ Could not read {MODEL_CARDS_FILE}: {e}", file=sys.stderr)
    return {}

def _save_model_cards(cards):
    _atomic_write_json(MODEL_CARDS_FILE, cards)

DEFAULT_PROMPT = "Explain how Mixture of Experts models work."


def apply_theme(root):
    s = ttk.Style(root)
    s.theme_use("clam")
    s.configure(".", background=BG, foreground=FG, fieldbackground=BG3, 
                bordercolor=BORDER, troughcolor=BG2, selectbackground=ACCENT,
                selectforeground=BG, insertcolor=FG, relief="flat")
    s.configure("TFrame", background=BG)
    s.configure("TLabel", background=BG, foreground=FG)
    s.configure("TLabelframe", background=BG, foreground=FG, bordercolor=BORDER)
    s.configure("TLabelframe.Label", background=BG, foreground=ACCENT, font=("Segoe UI", 9, "bold"))
    s.configure("TEntry", fieldbackground=BG3, foreground=FG, bordercolor=BORDER, insertcolor=FG, relief="flat")
    s.map("TEntry", bordercolor=[("focus", ACCENT)])
    s.configure("TButton", background=BG4, foreground=FG, bordercolor=BORDER, focuscolor=BG4, padding=(8, 4), relief="flat")
    s.map("TButton", background=[("active", BG3), ("pressed", BG2)], foreground=[("active", FG)])
    s.configure("Accent.TButton", background=GREEN2, foreground=BG, bordercolor=GREEN, padding=(8, 4))
    s.map("Accent.TButton", background=[("active", GREEN)])
    s.configure("TCombobox", fieldbackground=BG3, background=BG4, foreground=FG, arrowcolor=FG, bordercolor=BORDER, relief="flat")
    s.map("TCombobox", fieldbackground=[("readonly", BG3)], selectbackground=[("readonly", ACCENT)], selectforeground=[("readonly", BG)])
    s.configure("TCheckbutton", background=BG, foreground=FG, focuscolor=BG, indicatorcolor=BG3, indicatorrelief="flat")
    s.map("TCheckbutton", background=[("active", BG)], indicatorcolor=[("selected", ACCENT), ("active", BG4)])
    s.configure("TScale", background=BG, troughcolor=BG3, slidercolor=ACCENT, bordercolor=BORDER)
    s.configure("TNotebook", background=BG2, bordercolor=BORDER, tabmargins=0)
    s.configure("TNotebook.Tab", background=BG3, foreground=FG, padding=(14, 6), bordercolor=BORDER)
    s.map("TNotebook.Tab", background=[("selected", BG4)], foreground=[("selected", FG)])
    s.configure("TScrollbar", background=BG3, troughcolor=BG2, bordercolor=BORDER, arrowcolor=FG, relief="flat")
    s.map("TScrollbar", background=[("active", BG4)])
    s.configure("TSeparator", background=BORDER)
    for name, colour in [("green", "#00ff88"), ("orange", "#ffaa00"), ("gold", "#ffcc00"), ("red", "#ff4444"), ("cyan", "#00ccff")]:
        s.configure(name + ".Horizontal.TProgressbar", troughcolor=BG3, background=colour, bordercolor=BORDER)
    root.configure(bg=BG)


def dark_text(parent, **kw):
    kw.setdefault("bg", BG3); kw.setdefault("fg", FG)
    kw.setdefault("insertbackground", FG); kw.setdefault("selectbackground", ACCENT)
    kw.setdefault("selectforeground", BG); kw.setdefault("relief", "flat")
    kw.setdefault("borderwidth", 1); kw.setdefault("highlightthickness", 1)
    kw.setdefault("highlightbackground", BORDER); kw.setdefault("highlightcolor", ACCENT)
    return tk.Text(parent, **kw)


def frame(parent, bg=None, **kw):
    return tk.Frame(parent, bg=bg or BG, **kw)


def sep(parent, color=BORDER, pady=4):
    f = frame(parent, bg=color, height=1)
    f.pack(fill="x", pady=pady)
    return f


def make_scrollable(parent):
    """
    Creates a scrollable container inside `parent`.
    Returns the inner content frame where widgets should be placed.
    The canvas width tracks the parent width so resizing works correctly.
    """
    outer = tk.Frame(parent, bg=BG)
    outer.pack(fill="both", expand=True)
    
    canvas = tk.Canvas(outer, bg=BG, highlightthickness=0, bd=0)
    scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
    
    content = tk.Frame(canvas, bg=BG)
    
    content.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    
    canvas_window = canvas.create_window((0, 0), window=content, anchor="nw")
    
    def _on_canvas_configure(event):
        canvas.itemconfig(canvas_window, width=event.width)
    canvas.bind("<Configure>", _on_canvas_configure)
    
    canvas.configure(yscrollcommand=scrollbar.set)
    
    scrollbar.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)
    
    # Mousewheel only scrolls THIS canvas, and only while the cursor is over it.
    # (bind_all is global and last-bound-wins across multiple scrollable panes —
    # with two tabs each calling make_scrollable(), this previously meant only
    # whichever tab was built LAST actually responded to the mouse wheel.)
    def _on_mousewheel(event):
        canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        return "break"

    def _bind_wheel(_event=None):
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

    def _unbind_wheel(_event=None):
        canvas.unbind_all("<MouseWheel>")

    canvas.bind("<Enter>", _bind_wheel)
    canvas.bind("<Leave>", _unbind_wheel)

    return content


class LlamaLauncher(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("🦙 LLaMA Server Launcher")
        self.geometry("1400x900")
        self.minsize(1200, 700)
        self.configure(bg=BG)
        apply_theme(self)

        self.process = None
        self._cfg_dir = _CFG_DIR
        self._mem_poll_id = None
        self._mem_enabled = tk.BooleanVar(value=True)
        self._mem_interval = 2000
        self.settings = {}
        self.saved_configs = {}
        self.gpu_info = []
        self.gpu_vars = {}
        self._test_running = False
        self._best_tks = 0.0
        self._debounce_id = None
        # ── Per-model card data (manual edits) ────────────────
        self.model_cards = _load_model_cards()

        self.spec_type_var = tk.StringVar(value="none")
        self.spec_draft_model_var = tk.StringVar(value="")
        self.spec_draft_n_max_var = tk.StringVar(value="3")
        self.spec_draft_p_min_var = tk.StringVar(value="0.9")
        self.jinja_var = tk.BooleanVar(value=False)
        self.mtp_var = tk.StringVar(value="0")

        # Sampling parameter enable/disable variables
        self.enable_temp_var = tk.BooleanVar(value=True)
        self.enable_top_k_var = tk.BooleanVar(value=True)
        self.enable_top_p_var = tk.BooleanVar(value=True)
        self.enable_min_p_var = tk.BooleanVar(value=True)
        self.enable_repeat_p_var = tk.BooleanVar(value=True)
        self.enable_repeat_last_var = tk.BooleanVar(value=True)
        self.enable_presence_p_var = tk.BooleanVar(value=True)
        self.enable_frequency_p_var = tk.BooleanVar(value=True)
        self.enable_typical_var = tk.BooleanVar(value=True)

        self._load_settings()
        self._load_configs()
        self._build_ui()
        self._apply_settings()
        self._scan_models()
        # After UI is built and a model may have been restored from config, load its card
        if hasattr(self, "model_var") and self.model_var.get() and not self.model_var.get().startswith("("):
            self.after(100, self._refresh_model_card)
        self._detect_gpus()
        self._update_command()

    def _schedule_update(self, *_):
        if self._debounce_id:
            self.after_cancel(self._debounce_id)
        self._debounce_id = self.after(400, self._update_command)

    def _update_command(self, *_):
        self._debounce_id = None
        cmd = self._ps_command()
        self.cmd_text.configure(state="normal")
        self.cmd_text.delete("1.0", "end")
        self.cmd_text.insert("1.0", cmd)
        self.cmd_text.configure(state="disabled")
        self.exe_lbl.configure(text=self._exe_path())

    def _settings_file(self):
        return self._cfg_dir / "llama_settings.json"

    def _configs_file(self):
        return self._cfg_dir / "llama_configs.json"

    def _load_settings(self):
        try:
            sf = self._settings_file()
            if sf.exists():
                self.settings = json.loads(sf.read_text())
        except Exception as e:
            self.settings = {}
            print(f"⚠ Could not read settings file: {e}", file=sys.stderr)

    def _save_settings(self):
        self.settings["llama_dir"] = self.llama_dir_var.get()
        self.settings["models_dir"] = self.models_dir_var.get()
        _atomic_write_json(self._settings_file(), self.settings)

    def _apply_settings(self):
        self.llama_dir_var.set(self.settings.get("llama_dir", r"D:\llama"))
        self.models_dir_var.set(self.settings.get("models_dir", r"D:\llama\models"))

    def _scan_models(self):
        d = Path(self.models_dir_var.get())
        models = sorted([f.name for f in d.glob("*.gguf")]) if d.is_dir() else []
        cur = self.model_var.get()
        self.model_combo["values"] = models or ["(no models found)"]
        self.model_var.set(cur if cur in models else (models[0] if models else "(no models found)"))
        self._schedule_update()

    # ── Model Card / Metadata Parsing ────────────────────────────────
    def _find_model_source_folder(self, model_filename: str, models_dir: Path) -> Path | None:
        """
        Try to locate a source folder (e.g. HuggingFace repo) that contains
        metadata files for the given GGUF model.
        Strategy:
          1. Exact name match — a folder whose stem equals the gguf filename stem
          2. Partial match — any folder whose name is contained in the gguf name or vice versa
          3. Same-folder GGUF — if the GGUF itself has README.md / config.json alongside it
        """
        base = model_filename.replace(".gguf", "")
        candidates: list[Path] = []

        # Strategy 1 & 2: scan sibling folders in models_dir
        if models_dir.is_dir():
            for sub in models_dir.iterdir():
                if not sub.is_dir():
                    continue
                stem = sub.stem.lower()
                base_lower = base.lower()
                if stem == base_lower or stem in base_lower or base_lower in stem:
                    candidates.append(sub)

        # Strategy 3: GGUF sits alongside its own metadata
        gguf_path = models_dir / model_filename
        if (gguf_path.parent / "README.md").exists():
            candidates.insert(0, gguf_path.parent)  # prefer same-folder match

        for c in candidates:
            has_readme = (c / "README.md").exists()
            has_config = (c / "config.json").exists()
            if has_readme or has_config:
                return c
        return None

    def _parse_yaml_frontmatter(self, text: str) -> dict:
        """Extract YAML front-matter block from a string (e.g. README.md content)."""
        if HAS_YAML:
            try:
                result = yaml.safe_load(text)
                return result if isinstance(result, dict) else {}
            except Exception:
                pass
        # Regex fallback: extract between first --- and second ---
        m = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
        if m:
            try:
                import ast
                raw = m.group(1).strip()
                # Convert simple YAML to valid Python dict literal
                lines = [l for l in raw.splitlines() if l.strip() and not l.strip().startswith("---")]
                pairs: list[str] = []
                for line in lines:
                    stripped = line.rstrip()
                    colon_idx = stripped.find(":")
                    if colon_idx == -1:
                        continue
                    k, v = stripped[:colon_idx].strip(), stripped[colon_idx + 1:].strip()
                    # Handle list items like "- value"
                    if v.startswith("- "):
                        items = [x.strip().strip('"').strip("'") for x in v[2:].split(",")]
                        v = str(items)
                    elif not v:
                        v = "None"
                    elif v.lower() in ("true", "false"):
                        v = v.capitalize()
                    elif v.lower() in ("none", "null"):
                        v = "None"
                    elif re.match(r"^-?\d+(\.\d+)?$", v):
                        pass  # numeric literal — leave bare
                    elif not v.startswith(("[", "{", '"', "'")):
                        # Bare scalar string (e.g. "license: apache-2.0") MUST be
                        # quoted or ast.literal_eval rejects the entire dict literal.
                        v = repr(v.strip('"').strip("'"))
                    pairs.append(f'{k!r}: {v}')
                if pairs:
                    return dict(ast.literal_eval("{" + ", ".join(pairs) + "}"))
            except Exception:
                pass
        return {}

    def _parse_model_card(self, source_folder: Path | None, model_filename: str) -> dict:
        """
        Parse model card metadata from a source folder.
        Returns a flat dict of useful fields for display.
        """
        result: dict[str, object] = {}
        if not source_folder or not source_folder.is_dir():
            return result

        # ── Strategy A: huggingface_hub.ModelCard ────────────────
        readme_path = source_folder / "README.md"
        if HAS_HF_HUB and readme_path.exists():
            try:
                card = HFModelCard.load(readme_path)
                hf_data = card.data.to_dict() or {}
                # Flatten nested keys
                for k, v in hf_data.items():
                    if isinstance(v, (dict, list)):
                        result[k] = str(v)[:200]
                    else:
                        result[k] = v
            except Exception:
                pass  # fall through to manual parsing

        # ── Strategy B: manual YAML front-matter fallback ────────
        if not result and readme_path.exists():
            try:
                raw = readme_path.read_text(encoding="utf-8", errors="replace")
                fm = self._parse_yaml_frontmatter(raw)
                for k, v in fm.items():
                    result[k] = v
            except Exception:
                pass

        # ── Strategy C: config.json augmentation (always) ────────
        config_path = source_folder / "config.json"
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)

                # Architecture & type
                archs = cfg.get("architectures", [])
                result["architecture"] = archs[0] if isinstance(archs, list) and archs else cfg.get("architectures", "Unknown")
                result["model_type"] = cfg.get("model_type", result.get("model_type", "Unknown"))

                # Size / vocab — rough dense-transformer estimate:
                # embeddings (vocab*hidden) + per-layer attention (~4*hidden^2)
                # + per-layer MLP (~3*hidden*intermediate, e.g. SwiGLU).
                # This is an ESTIMATE — it ignores GQA head-count savings, MoE
                # active-vs-total params, and tied embeddings, so it's ballpark
                # only, not an authoritative count. (Previous version multiplied
                # num_hidden_layers into the total twice and silently produced
                # wrong numbers for common model shapes.)
                hidden = cfg.get("hidden_size", 0)
                layers = cfg.get("num_hidden_layers", 0)
                vocab = cfg.get("vocab_size", 0)
                intermediate = cfg.get("intermediate_size", hidden * 4)
                if hidden and layers:
                    attn_params = 4 * hidden * hidden
                    mlp_params = 3 * hidden * intermediate
                    embed_params = vocab * hidden
                    total_params = embed_params + layers * (attn_params + mlp_params)
                    if total_params > 1e9:
                        result["params"] = f"~{total_params / 1e9:.1f}B (est.)"
                    elif total_params > 1e6:
                        result["params"] = f"~{total_params / 1e6:.0f}M (est.)"

                vocab = cfg.get("vocab_size")
                if vocab and "vocab_size" not in result:
                    result["vocab_size"] = vocab

                # Tokenizer info
                tokenizer_cls = cfg.get("tokenizer_class", "")
                if tokenizer_cls:
                    result["tokenizer"] = tokenizer_cls

                # Quant / format hints from keys
                for key in cfg:
                    k_lower = key.lower()
                    if "quant" in k_lower or "dtype" in k_lower:
                        result[key] = str(cfg[key])[:100]
            except Exception:
                pass

        # ── Format hint from filename ────────────────────────────
        fn_lower = model_filename.lower()
        if "q4_0" in fn_lower or "q4f" in fn_lower:
            result["quant_format"] = "Q4_0"
        elif "q5" in fn_lower:
            result["quant_format"] = "Q5_xxx"
        elif "q8" in fn_lower:
            result["quant_format"] = "Q8_0"
        elif "f16" in fn_lower:
            result["quant_format"] = "F16"

        return result

    def _format_card_display(self, metadata: dict) -> str:
        """Format parsed metadata into a human-readable string for the text widget."""
        if not metadata:
            return "No model card data found.\n\nTip: place this GGUF inside a folder that has:\n  • README.md (with YAML front-matter) or\n  • config.json\nfrom the original HuggingFace repo."

        lines: list[str] = []

        # ── Manual card header (if manual data exists) ────────
        has_capability_arch = any(k.startswith("capability_") or k.startswith("arch_") for k in metadata)
        has_identity = any(k in ["display_name", "base_family"] for k in metadata)
        has_manual_card = has_capability_arch or has_identity
        if has_manual_card:
            display_name = metadata.get("display_name", "") or metadata.get("name", "")
            lines.append(f"Model: {display_name}")
            base_family = metadata.get("base_family", "")
            version = metadata.get("version", "")
            if base_family:
                line = f"Family: {base_family}"
                if version:
                    line += f" / v{version}"
                lines.append(line)
            params = metadata.get("params", "")
            quant = metadata.get("quant_format", "")
            fsz = metadata.get("file_size", "")
            info_parts = [p for p in [quant, str(params), fsz] if p]
            if info_parts:
                lines.append(f"Quant: {info_parts[0]} | Params: {info_parts[1]} | Size: {info_parts[2]}")
            lines.append("")  # separator
        else:
            # Auto-detected data (quant/size from filename + disk, params from config.json)
            quant = metadata.get("quant_format", "")
            fsz = metadata.get("file_size", "")
            params = metadata.get("params", "")
            parts: list[str] = []
            if quant:
                parts.append(f"Quant: {quant}")
            if params:
                parts.append(f"Params: {params}")
            if fsz:
                parts.append(f"Size: {fsz}")
            if parts:
                lines.append(" | ".join(parts))
                lines.append("")

        # ── Capabilities (from manual card) ───────────────────
        caps = []
        for k in metadata:
            if k.startswith("capability_") and metadata[k]:
                cap_name = k.replace("capability_", "").replace("_", " ").title()
                caps.append(cap_name)
        # Also check manual_ prefixed keys for capability-like fields
        for k in metadata:
            if k.startswith("manual_thinking") or k.startswith("manual_vision") or k.startswith("manual_audio") or \
               k.startswith("manual_code") or k.startswith("manual_math") or k.startswith("manual_json_mode") or \
               k.startswith("manual_tool_use") or k.startswith("manual_web_search") or k.startswith("manual_image_gen"):
                if isinstance(metadata[k], bool) and metadata[k]:
                    cap_name = k.replace("manual_", "").replace("_", " ").title()
                    caps.append(cap_name)
        if caps:
            lines.append(f"Capabilities: {', '.join(caps)}")
            lines.append("")  # separator

        # ── Architecture flags (from manual card) ─────────────
        archs = []
        for k in metadata:
            if k.startswith("arch_") and metadata[k]:
                flag_name = k.replace("arch_", "").replace("_", " ").title()
                if "moe" in k.lower(): archs.append("MoE")
                elif "spec" in k.lower(): archs.append("Speculative Decoding")
                elif "mtp" in k.lower(): archs.append("Multi-Token Prediction")
                elif "flash" in k.lower(): archs.append("Flash Attention")
                elif "mllock" in k.lower(): archs.append("MLock")
                elif "nommap" in k.lower(): archs.append("No-MMap")
        # Also check manual_ prefixed keys for architecture-like fields
        for k in metadata:
            if k.startswith("manual_moe_flag") or k.startswith("manual_spec_dec") or k.startswith("manual_mtp_flag") or \
               k.startswith("manual_flash_attn") or k.startswith("manual_mllock") or k.startswith("manual_nommap_flag"):
                if isinstance(metadata[k], bool) and metadata[k]:
                    label = k.replace("manual_", "").replace("_", " ").title()
                    if "moe" in k.lower(): archs.append("MoE")
                    elif "spec" in k.lower(): archs.append("Speculative Decoding")
                    elif "mtp" in k.lower(): archs.append("Multi-Token Prediction")
                    elif "flash" in k.lower(): archs.append("Flash Attention")
                    elif "mllock" in k.lower(): archs.append("MLock")
                    elif "nommap" in k.lower(): archs.append("No-MMap")
        if archs:
            lines.append(f"Architecture: {', '.join(archs)}")
            lines.append("")  # separator

        # ── Context / Tokenizer (from manual card) ────────────
        ctx = metadata.get("max_context", "") or metadata.get("manual_max_context", "")
        tok = metadata.get("tokenizer", "") or metadata.get("manual_tokenizer", "")
        if ctx or tok:
            parts = []
            if ctx: parts.append(f"Context: {ctx}")
            if tok: parts.append(f"Tokenizer: {tok}")
            lines.append(" | ".join(parts))
            lines.append("")  # separator

        # ── Auto-detected data (from source folder / filename) ──
        label_map = {
            "model_name": "Name",
            "name": "Name",
            "base_model_processing": "Base Model",
            "library_name": "Library",
            "library_version": "Lib Version",
            "license": "License",
            "pipeline_tag": "Pipeline",
            "tags": "Tags",
            "architecture": "Architecture",
            "model_type": "Model Type",
            "params": "Parameters",
            "hidden_size": "Hidden Size",
            "num_hidden_layers": "Num Layers",
            "num_attention_heads": "Attention Heads",
            "num_key_value_heads": "KV Heads",
            "intermediate_size": "Intermediate Size",
            "vocab_size": "Vocab Size",
            "tokenizer_class": "Tokenizer",
            "quant_format": "Quant Format",
        }

        seen_keys: set[str] = set()
        for key in ["model_name", "name", "base_model_processing", "library_name", "library_version",
                     "license", "pipeline_tag", "tags", "architecture", "model_type", "params",
                     "hidden_size", "num_hidden_layers", "num_attention_heads", "num_key_value_heads",
                     "intermediate_size", "vocab_size", "tokenizer_class", "quant_format"]:
            if key in metadata and key not in seen_keys:
                label = label_map.get(key, key.replace("_", " ").title())
                val = str(metadata[key])
                # Truncate long values
                if len(val) > 120:
                    val = val[:117] + "..."
                lines.append(f"{label}: {val}")
                seen_keys.add(key)

        # Dump any remaining keys we haven't displayed yet (skip manual keys already shown above)
        for key, val in metadata.items():
            if key not in seen_keys and not key.startswith("capability_") and not key.startswith("arch_"):
                label = key.replace("_", " ").title()
                val_str = str(val)[:120]
                lines.append(f"{label}: {val_str}")
                seen_keys.add(key)

        return "\n".join(lines) if lines else "No model card data found."

    # ── Styled / tagged display builder ───────────────────────────────
    def _build_tagged_lines(self, metadata: dict) -> list:
        """
        Build a list of styled rows for the MODEL INFO panel.
        Each row is either:
          - None  → section divider line
          - (emoji, label_fg, [(text, tag_name), ...])  → one or more text segments with tags
        Returns also a dict of {tag_name: {'foreground': color, 'font': ('family', size)}}
        """
        if not metadata:
            return None  # signals empty state

        rows = []
        tags = {}

        def _add_row(emoji, label_fg, *segments):
            """segments: list of (text, tag_name) tuples."""
            rows.append((emoji, label_fg, segments))

        def _tag(name, fg=FG, bg=None, fontname="Consolas", fontsize=9, bold=False):
            tags[name] = {"foreground": fg}
            if bg:
                tags[name]["background"] = bg
            tags[name]["font"] = (fontname, fontsize, "bold" if bold else "normal")

        # ── Tag definitions ────────────────────────────────────────
        _tag("emoji", FG2, None, "Segoe UI", 10)
        _tag("label_gold", GOLD, BG3, "Consolas", 9, True)
        _tag("label_green", ACCENT, BG3, "Consolas", 9, True)
        _tag("label_blue", BLUE, BG3, "Consolas", 9, True)
        _tag("label_red", RED, BG3, "Consolas", 9, True)
        _tag("label_teal", TEAL, BG3, "Consolas", 9, True)
        _tag("label_gray", FG2, BG3, "Consolas", 8)
        _tag("value", FG, None, "Consolas", 9)
        _tag("value_bold", FG, None, "Consolas", 9, True)
        _tag("divider", FG2, BG2, "Consolas", 7)

        # ── Section: Identity / Model info ─────────────────────────
        has_manual_card = any(k.startswith("capability_") or k.startswith("arch_") for k in metadata) or \
                          any(k in ["display_name", "base_family"] for k in metadata)

        if has_manual_card:
            display_name = metadata.get("display_name", "") or metadata.get("name", "")
            base_family = metadata.get("base_family", "")
            version = metadata.get("version", "")

            if display_name:
                _add_row("📖", FG2, (f" {display_name}", "value_bold"))
            if base_family or version:
                fam_ver = base_family
                if version:
                    fam_ver += f" / v{version}"
                _add_row("  └─", GOLD, (fam_ver, "label_gold"))

        # ── Quant / Params / Size row ──────────────────────────────
            quant = metadata.get("quant_format", "")
            params = metadata.get("params", "")
            fsz = metadata.get("file_size", "")
            info_parts = []
            if quant:
                _add_row("⚙️ ", ACCENT, (f"Quant: {quant}", "label_green"))
            if params:
                _add_row("💾 ", ACCENT, (f"Params: {params}", "label_green"))
            if fsz:
                _add_row("📏 ", FG2, (f"Size: {fsz}", "label_gray"))
        else:
            # Auto-detected only
            quant = metadata.get("quant_format", "")
            params = metadata.get("params", "")
            fsz = metadata.get("file_size", "")
            if quant or params or fsz:
                _add_row("📖 ", FG2, ("Auto-detected model info", "label_gray"))
            if quant:
                _add_row("⚙️ ", ACCENT, (f"Quant: {quant}", "label_green"))
            if params:
                _add_row("💾 ", ACCENT, (f"Params: {params}", "label_green"))
            if fsz:
                _add_row("📏 ", FG2, (f"Size: {fsz}", "label_gray"))

        rows.append(None)  # divider

        # ── Capabilities ───────────────────────────────────────────
        caps = []
        for k in metadata:
            if k.startswith("capability_") and metadata[k]:
                cap_name = k.replace("capability_", "").replace("_", " ").title()
                caps.append(cap_name)
        for k in metadata:
            manual_caps = ["thinking", "vision", "audio", "code", "math",
                           "json_mode", "tool_use", "web_search", "image_gen"]
            if any(k.startswith("manual_" + mc) for mc in manual_caps):
                if isinstance(metadata[k], bool) and metadata[k]:
                    cap_name = k.replace("manual_", "").replace("_", " ").title()
                    caps.append(cap_name)
        if caps:
            _add_row("✨ ", BLUE, ("Capabilities: " + ", ".join(caps), "label_blue"))
            rows.append(None)

        # ── Architecture flags ─────────────────────────────────────
        archs = []
        for k in metadata:
            if k.startswith("arch_") and metadata[k]:
                flag_name = k.replace("arch_", "").replace("_", " ").title()
                if "moe" in k.lower():
                    archs.append(f"MoE")
                elif "spec" in k.lower():
                    archs.append("Speculative Decoding")
                elif "mtp" in k.lower():
                    archs.append("Multi-Token Prediction")
                elif "flash" in k.lower():
                    archs.append("Flash Attention")
                elif "mllock" in k.lower():
                    archs.append("MLock")
                elif "nommap" in k.lower():
                    archs.append("No-MMap")
        for k in metadata:
            manual_archs = ["moe_flag", "spec_dec", "mtp_flag",
                            "flash_attn", "mllock", "nommap_flag"]
            if any(k.startswith("manual_" + ma) for ma in manual_archs):
                if isinstance(metadata[k], bool) and metadata[k]:
                    if "moe" in k.lower():
                        archs.append("MoE")
                    elif "spec" in k.lower():
                        archs.append("Speculative Decoding")
                    elif "mtp" in k.lower():
                        archs.append("Multi-Token Prediction")
                    elif "flash" in k.lower():
                        archs.append("Flash Attention")
                    elif "mllock" in k.lower():
                        archs.append("MLock")
                    elif "nommap" in k.lower():
                        archs.append("No-MMap")
        if archs:
            _add_row("🔎 ", RED, (f"Architecture: {', '.join(archs)}", "label_red"))
            rows.append(None)

        # ── Context / Tokenizer ────────────────────────────────────
        ctx = metadata.get("max_context", "") or metadata.get("manual_max_context", "")
        tok = metadata.get("tokenizer", "") or metadata.get("manual_tokenizer", "")
        if ctx or tok:
            parts = []
            if ctx:
                _add_row("📐 ", TEAL, (f"Context: {ctx}", "label_teal"))
            if tok:
                _add_row("🧠 ", TEAL, (f"Tokenizer: {tok}", "label_teal"))
            rows.append(None)

        # ── Auto-detected source data ──────────────────────────────
        label_map = {
            "model_name": "Name", "name": "Name",
            "base_model_processing": "Base Model", "library_name": "Library",
            "library_version": "Lib Version", "license": "License",
            "pipeline_tag": "Pipeline", "tags": "Tags",
            "architecture": "Architecture", "model_type": "Model Type",
            "params": "Parameters", "hidden_size": "Hidden Size",
            "num_hidden_layers": "Num Layers", "num_attention_heads": "Attention Heads",
            "num_key_value_heads": "KV Heads", "intermediate_size": "Intermediate Size",
            "vocab_size": "Vocab Size", "tokenizer_class": "Tokenizer",
            "quant_format": "Quant Format",
        }

        seen_keys: set[str] = set()
        for key in ["model_name", "name", "base_model_processing", "library_name",
                     "library_version", "license", "pipeline_tag", "tags",
                     "architecture", "model_type", "params",
                     "hidden_size", "num_hidden_layers", "num_attention_heads",
                     "num_key_value_heads", "intermediate_size", "vocab_size",
                     "tokenizer_class", "quant_format"]:
            if key in metadata and key not in seen_keys:
                label = label_map.get(key, key.replace("_", " ").title())
                val = str(metadata[key])
                if len(val) > 120:
                    val = val[:117] + "..."
                _add_row("  • ", FG2, (f"{label}: {val}", "label_gray"))
                seen_keys.add(key)

        # Dump remaining keys not yet displayed
        for key, val in metadata.items():
            if key not in seen_keys and not key.startswith("capability_") and not key.startswith("arch_"):
                label = key.replace("_", " ").title()
                val_str = str(val)[:120]
                _add_row("  • ", FG2, (f"{label}: {val_str}", "label_gray"))
                seen_keys.add(key)

        return rows, tags

    def _on_model_selected(self, *_):
        """Triggered when user selects a GGUF model — load and display its card."""
        model_name = self.model_var.get()
        if not model_name or model_name == "(no models found)":
            return
        if not model_name.endswith(".gguf"):
            return

        # ── Reload manual cards from disk to ensure fresh state ──
        self.model_cards = _load_model_cards()

        # ── Look up manual card — try exact match first, then case-insensitive fallback ──
        manual_card = self.model_cards.get(model_name, {})
        if not manual_card:
            # Case-insensitive / partial key search
            for k in self.model_cards:
                if k.lower() == model_name.lower():
                    manual_card = self.model_cards[k]
                    break
            if not manual_card:
                # Also try without .gguf extension
                base = model_name[:-5]  # strip .gguf
                for k in self.model_cards:
                    if k.replace(".gguf", "").lower() == base.lower():
                        manual_card = self.model_cards[k]
                        break
        has_manual = bool(manual_card)

        models_dir = Path(self.models_dir_var.get())
        source_folder = self._find_model_source_folder(model_name, models_dir)
        metadata = self._parse_model_card(source_folder, model_name)

        # ── Fallback when no source folder + no manual card: still show quant + file size from the GGUF itself ──
        if not metadata:
            gguf_path = Path(self.models_dir_var.get()) / model_name
            if gguf_path.exists():
                # Auto-detect quant format from filename
                fn_lower = model_name.lower()
                if any(q in fn_lower for q in ["q1_k", "q2_k"]):
                    metadata["quant_format"] = "Q1_K / Q2_K"
                elif "q3_km" in fn_lower:
                    metadata["quant_format"] = "Q3_KM"
                elif "q4_0" in fn_lower or "q4f" in fn_lower:
                    metadata["quant_format"] = "Q4_0"
                elif "q4_k_s" in fn_lower or "q4ks" in fn_lower:
                    metadata["quant_format"] = "Q4_K_S"
                elif "q4_k_m" in fn_lower or "q4km" in fn_lower:
                    metadata["quant_format"] = "Q4_K_M"
                elif "q5_0" in fn_lower:
                    metadata["quant_format"] = "Q5_0"
                elif "q5_k_s" in fn_lower or "q5ks" in fn_lower:
                    metadata["quant_format"] = "Q5_K_S"
                elif "q5_k_m" in fn_lower or "q5km" in fn_lower:
                    metadata["quant_format"] = "Q5_K_M"
                elif "q8_0" in fn_lower:
                    metadata["quant_format"] = "Q8_0"
                elif "f16" in fn_lower:
                    metadata["quant_format"] = "F16"
                elif "f32" in fn_lower:
                    metadata["quant_format"] = "F32"
                # File size from disk
                try:
                    sz = gguf_path.stat().st_size
                    if sz >= 1e9:
                        metadata["file_size"] = f"{sz / 1e9:.2f} GB"
                    elif sz >= 1e6:
                        metadata["file_size"] = f"{sz / 1e6:.0f} MB"
                    else:
                        metadata["file_size"] = f"{sz // 1024} KB"
                except Exception:
                    pass

        # Merge: manual card overrides auto-detected where available
        if has_manual:
            for key in ["display_name", "base_family", "version", "params",
                        "quant_format", "file_size", "max_context", "tokenizer"]:
                val = manual_card.get(key)
                if val is not None and isinstance(val, str) and val.strip():
                    metadata[key] = val
            # Merge ALL other keys too (description, tags, custom fields, etc.)
            for key in manual_card:
                if key in ["display_name", "base_family", "version", "params",
                           "quant_format", "file_size", "max_context", "tokenizer"]:
                    continue
                val = manual_card[key]
                if isinstance(val, bool):
                    metadata["manual_" + key] = val
                elif isinstance(val, str) and val.strip():
                    metadata["manual_" + key] = val
            for key in ["thinking", "vision", "audio", "code",
                        "math", "json_mode", "tool_use", "web_search",
                        "image_gen"]:
                if manual_card.get(key):
                    metadata["capability_" + key] = True
            for key in ["moe_flag", "spec_dec", "mtp_flag",
                        "flash_attn", "mllock", "nommap_flag"]:
                if manual_card.get(key):
                    metadata["arch_" + key] = True

        # ── Build styled / tagged rows for the info panel ────────
        result = self._build_tagged_lines(metadata)

        # Update the info panel with tags
        self.model_info_text.configure(state="normal")
        self.model_info_text.delete("1.0", "end")
        if result is None:
            # Empty metadata — show fallback message
            msg = ("No model card data found.\n"
                   "\nTip: place this GGUF inside a folder that has:\n"
                   "  • README.md (with YAML front-matter) or\n"
                   "  • config.json\nfrom the original HuggingFace repo.")
            self.model_info_text.insert("1.0", msg)
        else:
            rows, tags = result
            # Apply tag configurations to the text widget
            for tag_name, props in tags.items():
                self.model_info_text.tag_configure(tag_name, **props)
            for row in rows:
                if row is None:
                    # Divider line
                    self.model_info_text.insert("end", "─" * 48 + "\n", "divider")
                else:
                    emoji, label_fg, segments = row
                    # Emoji segment
                    self.model_info_text.insert("end", emoji, "emoji")
                    for text, tag_name in segments:
                        self.model_info_text.insert("end", text, tag_name)
                    self.model_info_text.insert("end", "\n")
        self.model_info_text.configure(state="disabled")

        # Update status label
        if metadata:
            parts = []
            source_type = "Manual" if has_manual else ("Auto" if not source_folder else "Source")
            params = metadata.get("params", "")
            qf = metadata.get("quant_format", "")
            arch_flags = [k.replace("arch_", "") for k in metadata if k.startswith("arch_")]
            caps = [k.replace("capability_", "") for k in metadata if k.startswith("capability_")]
            if qf: parts.append(f"Quant: {qf}")
            if params: parts.append(params)
            if arch_flags:
                # Show MoE/arch flags
                arch_display = []
                for f in arch_flags:
                    label = f.replace("_", " ").title()
                    if "moe" in f.lower(): arch_display.append("MoE")
                    elif "spec" in f.lower(): arch_display.append("Spec")
                    elif "mtp" in f.lower(): arch_display.append("MTP")
                    elif "flash" in f.lower(): arch_display.append("Flash")
                if arch_display: parts.append(" | ".join(arch_display))
            if caps:
                cap_labels = []
                for c in caps[:4]:  # show up to 4
                    label = c.replace("_", " ").title()
                    if len(label) > 12: label = label[:10] + "…"
                    cap_labels.append(label)
                parts.append(" | ".join(cap_labels))
            self.model_info_status.configure(text=f"● {source_type} card — {' | '.join(parts)}", fg=ACCENT if has_manual else FG2)
        else:
            self.model_info_status.configure(text="○ No card data — place README.md / config.json near the GGUF", fg=FG2)

    # ── Model Card Editor Dialog ───────────────────────────────
    _CAPABILITY_FLAGS = [
        ("Thinking / Reasoning", "thinking_var", False),
        ("Vision (Image)", "vision_var", False),
        ("Audio (Speech)", "audio_var", False),
        ("Code Generation", "code_var", False),
        ("Math Optimized", "math_var", False),
        ("JSON Mode", "json_mode_var", False),
        ("Tool / Function Calling", "tool_use_var", False),
        ("Web Search", "web_search_var", False),
        ("Image Generation", "image_gen_var", False),
    ]
    _ARCH_FLAGS = [
        ("MoE (Mixture of Experts)", "moe_flag_var", False),
        ("Speculative Decoding", "spec_dec_var", False),
        ("Multi-Token Prediction", "mtp_flag_var", False),
        ("Flash Attention", "flash_attn_var", True),
        ("MLock", "mllock_var", False),
        ("No-MMap", "nommap_flag_var", False),
    ]

    def _edit_model_card(self):
        model_name = self.model_var.get()
        if not model_name or model_name == "(no models found)" or not model_name.endswith(".gguf"):
            messagebox.showwarning("No Model", "Select a GGUF model first.")
            return

        existing = self.model_cards.get(model_name, {})
        dlg = tk.Toplevel(self)
        dlg.title(f"✏️ Edit Card — {model_name}")
        dlg.geometry("620x750")
        dlg.configure(bg=BG)
        dlg.transient(self)
        dlg.grab_set()

        # ── Use plain tk.Frame tabs (ttk Notebook bordercolor breaks on Windows) ──
        tab_names = ["Identity", "Quantization", "Capabilities", "Architecture", "Context / Tokenizer"]

        top_frame = tk.Frame(dlg, bg=BG)
        top_frame.pack(fill="x", padx=8, pady=(8, 0))

        tab_btns = []
        for i, name in enumerate(tab_names):
            btn = tk.Button(top_frame, text=name, bg=BG3, fg=FG2,
                            activebackground=BG4, relief="flat", bd=1,
                            font=("Segoe UI", 8), width=16)
            btn.pack(side="left", padx=2)
            tab_btns.append(btn)

        # Container for tab content (overlapping frames)
        tab_container = tk.Frame(dlg, bg=BG)
        tab_container.pack(fill="both", expand=True, padx=8, pady=(4, 0))

        all_tabs = {}
        for name in tab_names:
            f = tk.Frame(tab_container, bg=BG)
            f.place(x=0, y=0, relwidth=1.0, relheight=1.0)
            all_tabs[name] = f

        def _show_tab(idx):
            for i, (name, frame) in enumerate(all_tabs.items()):
                if i == idx:
                    frame.place(relx=0, rely=0, relwidth=1.0, relheight=1.0)
                else:
                    frame.place_forget()
            for i, btn in enumerate(tab_btns):
                bg = BG4 if i == idx else BG3
                fg = FG if i == idx else FG2
                btn.configure(bg=bg, fg=fg)

        _show_tab(0)  # default: Identity tab

        for btn_idx, name in enumerate(tab_names):
            tab_btns[btn_idx].configure(command=lambda i=btn_idx: _show_tab(i))

        # ── Tab 1: Identity ────────────────────────────────────
        f1 = frame(all_tabs["Identity"])
        f1.place(relx=0, rely=0, relwidth=1.0, relheight=1.0)
        f1.columnconfigure(0, weight=0)  # labels don't expand
        f1.columnconfigure(1, weight=1)  # entries expand

        def _entry_row(parent, r, label_text, var_name, default="", width=30, values=None):
            tk.Label(parent, text=label_text, bg=BG, fg=FG2, anchor="e", width=18).grid(row=r, column=0, padx=(0, 4), pady=4, sticky="e")
            v = tk.StringVar(value=default)
            setattr(self, f"_card_{var_name}", v)
            if values is not None:
                cb = ttk.Combobox(parent, textvariable=v, values=values, font=("Consolas", 9),
                                  state="readonly", width=width)
                cb.grid(row=r, column=1, padx=(0, 4), pady=4, sticky="ew")
            else:
                e = tk.Entry(parent, textvariable=v, bg=BG3, fg=FG, insertbackground=FG,
                             relief="flat", bd=1, width=width, font=("Consolas", 9))
                e.grid(row=r, column=1, padx=(0, 4), pady=4, sticky="ew")

        _entry_row(f1, 0, "Display Name:", "display_name", existing.get("display_name", model_name.replace(".gguf", "")))
        _entry_row(f1, 1, "Base Family:", "base_family", existing.get("base_family", "Other"), width=20,
                   values=["Llama", "Mistral", "Gemma", "Phi", "Qwen", "Yi", "DeepSeek", "Dolphin", "Neural-Chat", "Other"])
        _entry_row(f1, 2, "Version / Variant:", "version_var", existing.get("version", ""))
        _entry_row(f1, 3, "Parameter Count:", "params_var", existing.get("params", ""), width=20)

        # ── Tab 2: Quantization ────────────────────────────────
        f2 = frame(all_tabs["Quantization"])
        f2.place(relx=0, rely=0, relwidth=1.0, relheight=1.0)
        f2.columnconfigure(0, weight=0)
        f2.columnconfigure(1, weight=1)

        tk.Label(f2, text="Quant Format:", bg=BG, fg=FG2, anchor="e", width=18).grid(row=0, column=0, padx=(8,4), pady=4, sticky="e")
        qf_var = tk.StringVar(value=existing.get("quant_format", ""))
        setattr(self, "_card_quant_format", qf_var)
        tk.Entry(f2, textvariable=qf_var, bg=BG3, fg=FG, insertbackground=FG, relief="flat", bd=1, width=20).grid(row=0, column=1, padx=4, pady=4, sticky="ew")

        tk.Label(f2, text="File Size:", bg=BG, fg=FG2, anchor="e", width=18).grid(row=1, column=0, padx=(8,4), pady=4, sticky="e")
        fs_var = tk.StringVar(value=existing.get("file_size", ""))
        setattr(self, "_card_file_size", fs_var)
        tk.Entry(f2, textvariable=fs_var, bg=BG3, fg=FG, insertbackground=FG, relief="flat", bd=1, width=20).grid(row=1, column=1, padx=4, pady=4, sticky="ew")

        # ── Tab 3: Capabilities (checkboxes) ───────────────────
        f3 = frame(all_tabs["Capabilities"])
        f3.place(relx=0, rely=0, relwidth=1.0, relheight=1.0)

        cap_vars = []
        for i, (txt, vname, default) in enumerate(self._CAPABILITY_FLAGS):
            row = i // 2
            col = i % 2
            var = tk.BooleanVar(value=existing.get(vname.replace("_var", ""), default))
            setattr(self, f"_card_{vname}", var)
            cap_vars.append((txt, var))
            tk.Checkbutton(f3, text=txt, variable=var, bg=BG, fg=FG,
                           activebackground=BG, selectcolor=BG3).grid(row=row, column=col, sticky="w", padx=(0, 12), pady=4)

        # ── Tab 4: Architecture Flags (checkboxes) ─────────────
        f4 = frame(all_tabs["Architecture"])
        f4.place(relx=0, rely=0, relwidth=1.0, relheight=1.0)

        arch_vars = []
        for i, (txt, vname, default) in enumerate(self._ARCH_FLAGS):
            row = i // 2
            col = i % 2
            var = tk.BooleanVar(value=existing.get(vname.replace("_var", ""), default))
            setattr(self, f"_card_{vname}", var)
            arch_vars.append((txt, var))
            tk.Checkbutton(f4, text=txt, variable=var, bg=BG, fg=FG,
                           activebackground=BG, selectcolor=BG3).grid(row=row, column=col, sticky="w", padx=(0, 12), pady=4)

        # ── Tab 5: Context & Tokenizer ─────────────────────────
        f5 = frame(all_tabs["Context / Tokenizer"])
        f5.place(relx=0, rely=0, relwidth=1.0, relheight=1.0)

        tk.Label(f5, text="Max Context:", bg=BG, fg=FG2, anchor="e", width=18).grid(row=0, column=0, padx=(8,4), pady=4, sticky="e")
        mc_var = tk.StringVar(value=existing.get("max_context", ""))
        setattr(self, "_card_max_ctx", mc_var)
        tk.Entry(f5, textvariable=mc_var, bg=BG3, fg=FG, insertbackground=FG, relief="flat", bd=1, width=20).grid(row=0, column=1, padx=4, pady=4, sticky="ew")

        tk.Label(f5, text="Tokenizer Type:", bg=BG, fg=FG2, anchor="e", width=18).grid(row=1, column=0, padx=(8,4), pady=4, sticky="e")
        tt_var = tk.StringVar(value=existing.get("tokenizer", ""))
        setattr(self, "_card_tokenizer_type", tt_var)
        tk.Entry(f5, textvariable=tt_var, bg=BG3, fg=FG, insertbackground=FG, relief="flat", bd=1, width=20).grid(row=1, column=1, padx=4, pady=4, sticky="ew")

        # ── Save / Cancel buttons ──────────────────────────────
        btn_frame = frame(dlg)
        btn_frame.pack(fill="x", pady=(8, 16))
        btn_save = tk.Button(btn_frame, text="💾 Save Card", bg=GREEN2, fg=BG,
                  activebackground=GREEN, relief="flat", bd=0, padx=14, pady=5,
                  font=("Segoe UI", 9, "bold"))
        btn_save.pack(side="left")

        def _on_save():
            self._save_model_card(dlg)
        btn_save.configure(command=_on_save)

        tk.Button(btn_frame, text="Cancel", bg=BG4, fg=FG2, relief="flat", bd=0, padx=14,
                  pady=5, font=("Segoe UI", 9), command=dlg.destroy).pack(side="right")

    def _save_model_card(self, dlg):
        model_name = self.model_var.get()
        if not model_name:
            return

        card = {
            "display_name": getattr(self, "_card_display_name", None).get() or "",
            "base_family": getattr(self, "_card_base_family", None).get() or "Other",
            "version": getattr(self, "_card_version_var", None).get() or "",
            "params": getattr(self, "_card_params_var", None).get() or "",
            "quant_format": getattr(self, "_card_quant_format", None).get() or "",
            "file_size": getattr(self, "_card_file_size", None).get() or "",
        }

        # Capabilities
        for _, vname, _ in self._CAPABILITY_FLAGS:
            var = getattr(self, f"_card_{vname}", None)
            if var is not None:
                card[vname.replace("_var", "")] = var.get()

        # Architecture flags
        for _, vname, _ in self._ARCH_FLAGS:
            var = getattr(self, f"_card_{vname}", None)
            if var is not None:
                card[vname.replace("_var", "")] = var.get()

        # Context / tokenizer
        card["max_context"] = getattr(self, "_card_max_ctx", None).get() or ""
        card["tokenizer"] = getattr(self, "_card_tokenizer_type", None).get() or ""

        self.model_cards[model_name] = card
        _save_model_cards(self.model_cards)
        dlg.destroy()
        # Re-display the card
        self._on_model_selected()

    def _refresh_model_card(self):
        """Re-load the current model's card (called after directory changes)."""
        if hasattr(self, "model_var") and self.model_var.get() and not self.model_var.get().startswith("("):
            self._on_model_selected()

    def _clear_model_card(self):
        """Clear the model info panel."""
        if hasattr(self, "model_info_text"):
            self.model_info_text.configure(state="normal")
            self.model_info_text.delete("1.0", "end")
            self.model_info_text.insert("1.0", "No model selected.")
            self.model_info_text.configure(state="disabled")

    def _detect_gpus(self):
        self.gpu_info = []
        try:
            r = subprocess.run(["nvidia-smi", "--query-gpu=index,name,memory.total,memory.free",
                              "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=10)
            for line in r.stdout.strip().splitlines():
                p = [x.strip() for x in line.split(",")]
                if len(p) >= 4:
                    self.gpu_info.append({"idx": p[0], "name": p[1], "vram_mib": int(p[2]), "free_mib": int(p[3])})
        except Exception as e:
            self._log(f"️ GPU detection: {e}\n")
        self._rebuild_gpu_rows()

    def _rebuild_gpu_rows(self):
        for w in self.gpu_frame.winfo_children():
            w.destroy()
        self.gpu_vars.clear()
        if not self.gpu_info:
            tk.Label(self.gpu_frame, text="No NVIDIA GPUs detected", bg=BG, fg=FG2).pack(side="left", padx=4)
            self._update_ts_visibility()
            return
        for gpu in self.gpu_info:
            var = tk.BooleanVar(value=(gpu["idx"] == "0"))
            self.gpu_vars[gpu["idx"]] = var
            row = frame(self.gpu_frame)
            row.pack(side="left", padx=(0, 16))
            tk.Checkbutton(row, variable=var, bg=BG, fg=FG, selectcolor=BG3, command=self._on_gpu_toggle).pack(side="left")
            tk.Label(row, text=f" GPU {gpu['idx']} ", bg="#1e3a5f", fg=ACCENT, font=("Segoe UI", 9, "bold"), padx=4).pack(side="left", padx=(2, 6))
            tk.Label(row, text=gpu["name"], bg=BG, fg=FG, font=("Segoe UI", 9)).pack(side="left", padx=(0, 8))
            tk.Label(row, text=f"{gpu['vram_mib']:,} MiB", bg=BG, fg=GREEN, font=("Segoe UI", 9)).pack(side="left")
            tk.Label(row, text=f" ({gpu['free_mib']:,} free)", bg=BG, fg=FG2, font=("Segoe UI", 8)).pack(side="left")
        self._on_gpu_toggle()

    def _on_gpu_toggle(self):
        self._update_ts_visibility()
        sel = self._selected_gpus()
        if len(sel) >= 2:
            lk = {g["idx"]: g for g in self.gpu_info}
            self.ts_var.set(",".join(str(lk[i]["vram_mib"]) for i in sel if i in lk))
        self._schedule_update()

    def _selected_gpus(self):
        return sorted([i for i, v in self.gpu_vars.items() if v.get()], key=int)

    def _update_ts_visibility(self):
        if len(self._selected_gpus()) >= 2:
            self.ts_row.pack(fill="x", pady=(4, 0))
        else:
            self.ts_row.pack_forget()

    def _build_ui(self):
        """Build UI with proper scrolling - no phantom windows"""
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=6, pady=6)

        # Server tab with scrolling
        server_tab = frame(nb)
        nb.add(server_tab, text="    Server  ")
        server_content = make_scrollable(server_tab)
        self._build_server_tab(server_content)

        # Test tab with scrolling
        test_tab = frame(nb)
        nb.add(test_tab, text="    Test Prompt  ")
        test_content = make_scrollable(test_tab)
        self._build_test_tab(test_content)

    def _build_server_tab(self, parent):
        self._build_setup(parent)
        mid = frame(parent)
        mid.pack(fill="both", expand=True, padx=6, pady=4)
        mid.columnconfigure(0, weight=1)
        mid.columnconfigure(1, weight=1)
        self._build_params(mid, col=0)
        self._build_command_configs(mid, col=1)
        self._build_advanced_perf(parent)
        self._build_launch_log(parent)

    def _build_advanced_perf(self, parent):
        outer = tk.LabelFrame(parent, text="  GPU / CPU / AUTO-FIT  ", bg=BG, fg=FG, font=("Segoe UI", 9, "bold"), bd=1, relief="groove")
        outer.pack(fill="x", padx=6, pady=(2,4))
        f = frame(outer)
        f.pack(fill="x", padx=4, pady=4)

        def erow2(col_base, r, text, var_name, default, width=10):
            var = tk.StringVar(value=default)
            setattr(self, var_name, var)
            var.trace_add("write", self._schedule_update)
            tk.Label(f, text=text, bg=BG, fg=FG, anchor="e", width=15).grid(row=r, column=col_base, padx=(8,4), pady=2, sticky="e")
            tk.Entry(f, textvariable=var, bg=BG3, fg=FG, insertbackground=FG, relief="flat", bd=1, width=width).grid(row=r, column=col_base+1, padx=4, pady=2, sticky="w")
            return var

        def crow2(col_base, r, text, var_name, default, values, width=10):
            var = tk.StringVar(value=default)
            setattr(self, var_name, var)
            tk.Label(f, text=text, bg=BG, fg=FG, anchor="e", width=15).grid(row=r, column=col_base, padx=(8,4), pady=2, sticky="e")
            cb = ttk.Combobox(f, textvariable=var, values=values, state="readonly", width=width)
            cb.grid(row=r, column=col_base+1, padx=4, pady=2, sticky="w")
            cb.bind("<<ComboboxSelected>>", lambda _: self._schedule_update())
            return cb

        # Block 1: Auto-fit (-fit) — llama.cpp's own VRAM-fitting logic
        tk.Label(f, text="Auto-Fit", bg=BG, fg=ACCENT, font=("Segoe UI", 9, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", padx=4)
        crow2(0, 1, "Fit (-fit):", "fit_var", "on", ["on","off"], width=6)
        erow2(0, 2, "Fit Target MiB:", "fit_target_var", "", width=10)
        erow2(0, 3, "Fit Min Ctx:", "fit_ctx_var", "", width=10)

        # Block 2: Multi-GPU placement
        tk.Label(f, text="Multi-GPU", bg=BG, fg=ACCENT, font=("Segoe UI", 9, "bold")).grid(row=0, column=2, columnspan=2, sticky="w", padx=(20,4))
        crow2(2, 1, "Split Mode (-sm):", "split_mode_var", "layer", ["none","layer","row","tensor"], width=8)
        erow2(2, 2, "Main GPU (-mg):", "main_gpu_var", "0", width=6)
        erow2(2, 3, "Override Tensor:", "override_tensor_var", "", width=18)

        # Block 3: NUMA / CPU affinity / repack
        tk.Label(f, text="NUMA / CPU", bg=BG, fg=ACCENT, font=("Segoe UI", 9, "bold")).grid(row=0, column=4, columnspan=2, sticky="w", padx=(20,4))
        crow2(4, 1, "NUMA:", "numa_var", "", ["","distribute","isolate","numactl"], width=10)
        erow2(4, 2, "CPU Range (-Cr):", "cpu_range_var", "", width=10)
        crow2(4, 3, "Repack:", "repack_choice_var", "on", ["on","off"], width=6)

        tk.Label(f, text="Leave Fit Target/Min Ctx/Main GPU/CPU Range blank to use llama-server's own defaults.",
                 bg=BG, fg=FG2, font=("Segoe UI", 8)).grid(row=4, column=0, columnspan=6, sticky="w", padx=8, pady=(6,2))

    def _build_setup(self, parent):
        outer = tk.LabelFrame(parent, text="  ⚙  SETUP — Remembered across sessions  ",
                              bg=BG, fg=GREEN, font=("Segoe UI", 9, "bold"), bd=1, relief="groove", labelanchor="nw")
        outer.pack(fill="x", padx=6, pady=(6, 2))

        def dir_row(f, row, text, var_name, default):
            var = tk.StringVar(value=default)
            setattr(self, var_name, var)
            var.trace_add("write", self._schedule_update)
            tk.Label(f, text=text, bg=BG, fg=FG2, width=16, anchor="e").grid(row=row, column=0, padx=(8,4), pady=4, sticky="e")
            e = tk.Entry(f, textvariable=var, bg=BG3, fg=FG, insertbackground=FG, relief="flat", bd=1, highlightthickness=1,
                        highlightbackground=BORDER, highlightcolor=ACCENT, font=("Consolas", 10))
            e.grid(row=row, column=1, padx=4, pady=4, sticky="ew")
            ttk.Button(f, text="Browse", width=7, command=lambda v=var: self._browse_dir(v)).grid(row=row, column=2, padx=4, pady=4)
            return var

        f = frame(outer)
        f.pack(fill="x")
        f.columnconfigure(1, weight=1)
        f.columnconfigure(4, weight=1)

        self.llama_dir_var = dir_row(f, 0, "LLaMA Directory:", "llama_dir_var", r"D:\llama")
        self.models_dir_var = dir_row(f, 1, "Models Directory:", "models_dir_var", r"D:\llama\models")

        tk.Label(f, text="exe:", bg=BG, fg=FG2).grid(row=0, column=3, padx=(12,4), sticky="e")
        self.exe_lbl = tk.Label(f, text="", bg=BG, fg=FG2, font=("Consolas", 9), anchor="w")
        self.exe_lbl.grid(row=0, column=4, padx=4, sticky="ew")

        tk.Button(f, text="✔ Save & Apply", bg=GREEN2, fg=BG, activebackground=GREEN, activeforeground=BG, relief="flat", bd=0,
                 padx=10, pady=4, font=("Segoe UI", 9, "bold"), command=self._apply_dirs).grid(row=0, column=5, padx=(4,10), pady=4, rowspan=1)

        tk.Label(f, text="Config Directory:", bg=BG, fg=FG2, width=16, anchor="e").grid(row=2, column=0, padx=(8,4), pady=4, sticky="e")
        self.cfg_dir_lbl = tk.Label(f, text=str(self._cfg_dir), bg=BG3, fg=ACCENT, font=("Consolas", 9), anchor="w", relief="flat", bd=1, padx=4)
        self.cfg_dir_lbl.grid(row=2, column=1, padx=4, pady=4, sticky="ew")
        ttk.Button(f, text="Change", width=7, command=self._change_cfg_dir).grid(row=2, column=2, padx=4, pady=4)
        tk.Label(f, text="(llama_settings.json + llama_configs.json saved here)", bg=BG, fg=FG2, font=("Segoe UI", 8)).grid(row=2, column=3, columnspan=3, padx=(12,4), sticky="w")

        tk.Label(f, text="Model:", bg=BG, fg=FG2).grid(row=3, column=3, padx=(12,4), sticky="e")
        mf = frame(f)
        mf.grid(row=3, column=4, padx=4, pady=4, sticky="ew")
        mf.columnconfigure(0, weight=1)
        self.model_var = tk.StringVar()
        self.model_combo = ttk.Combobox(mf, textvariable=self.model_var, font=("Consolas", 9), state="readonly")
        self.model_combo.grid(row=0, column=0, sticky="ew")
        self.model_combo.bind("<<ComboboxSelected>>", lambda _: (self._schedule_update(), self._on_model_selected()))
        ttk.Button(mf, text="🔄", width=3, command=self._scan_models).grid(row=0, column=1, padx=(2,0))
        tk.Button(mf, text="✏️ Edit Card", bg=BG4, fg=GOLD, relief="flat", bd=0, padx=6,
                  font=("Segoe UI", 8), command=self._edit_model_card).grid(row=0, column=2, padx=(2,0))

        # ── Model Info Panel ───────────────────────────────────────
        mi_outer = tk.LabelFrame(outer, text="  📖  MODEL INFO  ",
                                  bg=BG, fg=GOLD, font=("Segoe UI", 9, "bold"), bd=1, relief="groove")
        mi_outer.pack(fill="x", padx=8, pady=(4, 6))

        self.model_info_text = dark_text(mi_outer, height=5, wrap="word", font=("Consolas", 9), state="disabled")
        self.model_info_text.pack(fill="both", expand=True, padx=6, pady=(6, 2))

        sb_mi = ttk.Scrollbar(mi_outer, orient="vertical", command=self.model_info_text.yview)
        sb_mi.pack(side="right", fill="y")
        self.model_info_text.configure(yscrollcommand=sb_mi.set)

        self.model_info_status = tk.Label(mi_outer, text="○ No model selected.", bg=BG, fg=FG2,
                                          font=("Segoe UI", 8))
        self.model_info_status.pack(fill="x", padx=6, pady=(0, 4))

        gpu_outer = frame(outer)
        gpu_outer.pack(fill="x", padx=8, pady=(4, 6))
        gh = frame(gpu_outer)
        gh.pack(fill="x")
        tk.Label(gh, text="  GPUs", bg=BG, fg=GREEN, font=("Segoe UI", 9, "bold")).pack(side="left")
        tk.Label(gh, text="  Select GPU(s). Tick 2 to split across both.", bg=BG, fg=FG2, font=("Segoe UI", 9)).pack(side="left")
        tk.Button(gh, text="🔄 Detect", bg=BG4, fg=ACCENT, relief="flat", bd=0, padx=8, command=self._detect_gpus).pack(side="right")

        self.gpu_frame = frame(gpu_outer)
        self.gpu_frame.pack(fill="x", pady=(4, 0))

        self.ts_row = frame(gpu_outer, bg=BG2)
        tf = frame(self.ts_row, bg=BG2)
        tf.pack(fill="x", padx=6, pady=4)
        tk.Label(tf, text="Tensor Split (-ts):", bg=BG2, fg=ACCENT, font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0,8))
        self.ts_var = tk.StringVar()
        self.ts_var.trace_add("write", self._schedule_update)
        tk.Entry(tf, textvariable=self.ts_var, bg=BG3, fg=FG, insertbackground=FG, relief="flat", bd=1, font=("Consolas", 10), width=20).pack(side="left", padx=(0,8))
        tk.Label(tf, text="MiB per GPU — auto-filled from detected VRAM", bg=BG2, fg=FG2, font=("Segoe UI", 9)).pack(side="left")

    def _build_params(self, parent, col):
        outer = tk.LabelFrame(parent, text="  PARAMETERS  ", bg=BG, fg=FG, font=("Segoe UI", 9, "bold"), bd=1, relief="groove")
        outer.grid(row=0, column=col, sticky="nsew", padx=(0,3), pady=2)
        outer.columnconfigure(1, weight=1)

        def erow(r, text, var_name, default, width=12):
            var = tk.StringVar(value=default)
            setattr(self, var_name, var)
            var.trace_add("write", self._schedule_update)
            tk.Label(outer, text=text, bg=BG, fg=FG, anchor="e", width=18).grid(row=r, column=0, padx=(8,4), pady=2, sticky="e")
            e = tk.Entry(outer, textvariable=var, bg=BG3, fg=FG, insertbackground=FG, relief="flat", bd=1, highlightthickness=1,
                        highlightbackground=BORDER, highlightcolor=ACCENT, width=width)
            e.grid(row=r, column=1, padx=4, pady=2, sticky="w")
            return var

        def crow(r, text, var_name, default, values, width=14):
            var = tk.StringVar(value=default)
            setattr(self, var_name, var)
            tk.Label(outer, text=text, bg=BG, fg=FG, anchor="e", width=18).grid(row=r, column=0, padx=(8,4), pady=2, sticky="e")
            cb = ttk.Combobox(outer, textvariable=var, values=values, state="readonly", width=width)
            cb.grid(row=r, column=1, padx=4, pady=2, sticky="w")
            cb.bind("<<ComboboxSelected>>", lambda _: self._schedule_update())
            return cb

        r = 0
        erow(r, "GPU Layers (-ngl):", "ngl_var", "999")
        r += 1

        self.moe_var = tk.StringVar(value="25")
        self.moe_var.trace_add("write", self._schedule_update)
        tk.Label(outer, text="CPU MoE:", bg=BG, fg=FG, anchor="e", width=18).grid(row=r, column=0, padx=(8,4), pady=2, sticky="e")
        mf = frame(outer)
        mf.grid(row=r, column=1, sticky="ew", padx=4, pady=2)
        self.moe_slider = tk.Scale(mf, from_=0, to=100, orient="horizontal", variable=self.moe_var, bg=BG, fg=FG, troughcolor=BG3,
                                   activebackground=ACCENT, highlightthickness=0, sliderrelief="flat", length=120, showvalue=False,
                                   command=lambda v: self.moe_var.set(str(int(float(v)))))
        self.moe_slider.pack(side="left")
        tk.Entry(mf, textvariable=self.moe_var, bg=BG3, fg=FG, insertbackground=FG, relief="flat", bd=1, width=5).pack(side="left", padx=(4,0))
        r += 1

        # Full set = mainline llama.cpp KV cache types + turbo2/3/4 (only valid
        # on a self-built TurboQuant fork: github.com/TheTom/llama-cpp-turboquant).
        # Default is f16 so a fresh config or a mainline-build exe never gets
        # handed a cache type its binary doesn't recognize — turbo2/3/4 are an
        # explicit opt-in via the dropdown, not the default.
        _KV_CACHE_TYPES = ["f32", "f16", "bf16", "q8_0", "q4_0", "q4_1", "iq4_nl",
                            "q5_0", "q5_1", "turbo2", "turbo3", "turbo4"]
        crow(r, "KV Cache K (-ctk):", "ctk_var", "f16", _KV_CACHE_TYPES)
        r += 1
        crow(r, "KV Cache V (-ctv):", "ctv_var", "f16", _KV_CACHE_TYPES)
        r += 1
        tk.Label(outer, text="turbo2/3/4 require a self-built TurboQuant-fork llama-server.exe — will error on a mainline build.",
                 bg=BG, fg=FG2, font=("Segoe UI", 7)).grid(row=r, column=0, columnspan=2, sticky="w", padx=8, pady=(0,4))
        r += 1
        crow(r, "Context (-c):", "ctx_var", "258944", ["4096","8192","16384","32768","65536","131072","258944","262144"])
        r += 1
        
        erow(r, "Threads (-t):", "threads_var", "", width=8)
        r += 1
        erow(r, "Batch (-b):", "batch_var", "", width=8)
        r += 1
        erow(r, "uBatch (-ub):", "ubatch_var", "", width=8)
        r += 1
        erow(r, "Cache Reuse:", "srv_cache_reuse_var", "0", width=8)
        r += 1
        
        crow(r, "Parallel (-np):", "np_var", "", ["","1","2","4","8"], width=8)
        r += 1
        erow(r, "Host:", "host_var", "127.0.0.1", width=14)
        r += 1
        erow(r, "Port:", "port_var", "8080", width=8)
        r += 1

        # Speculative Decoding Section
        tk.Frame(outer, bg=BG4, height=1).grid(row=r, column=0, columnspan=2, sticky="ew", pady=6)
        r += 1
        tk.Label(outer, text="SPECULATIVE DECODING", bg=BG, fg=ACCENT, font=("Segoe UI", 9, "bold")).grid(row=r, column=0, columnspan=2, sticky="w", padx=8, pady=(0,4))
        r += 1
        tk.Label(outer, text="MTP Tokens > 0 takes priority (sets --spec-type draft-mtp).", bg=BG, fg=FG2, font=("Segoe UI", 8)).grid(row=r, column=0, columnspan=2, sticky="w", padx=8, pady=(0,2))
        r += 1
        erow(r, "MTP Tokens (0-6):", "mtp_var", "0", width=8)
        r += 1
        tk.Label(outer, text="Classic / N-gram (used only when MTP Tokens = 0):", bg=BG, fg=FG2, font=("Segoe UI", 8)).grid(row=r, column=0, columnspan=2, sticky="w", padx=8, pady=(4,2))
        r += 1
        crow(r, "Spec Type:", "spec_type_var", "none",
             ["none","draft-simple","draft-eagle3","ngram-simple","ngram-map-k","ngram-map-k4v","ngram-mod","ngram-cache"])
        r += 1
        tk.Label(outer, text="Draft Model:", bg=BG, fg=FG, anchor="e", width=18).grid(row=r, column=0, padx=(8,4), pady=2, sticky="e")
        dmf = frame(outer)
        dmf.grid(row=r, column=1, sticky="ew", padx=4, pady=2)
        self.spec_draft_model_var.trace_add("write", self._schedule_update)
        tk.Entry(dmf, textvariable=self.spec_draft_model_var, bg=BG3, fg=FG, insertbackground=FG, relief="flat", bd=1, width=16).pack(side="left", fill="x", expand=True)
        ttk.Button(dmf, text="…", width=3, command=self._browse_draft_model).pack(side="left", padx=(2,0))
        r += 1
        erow(r, "Draft N-Max:", "spec_draft_n_max_var", "3", width=8)
        r += 1
        erow(r, "Draft P-Min:", "spec_draft_p_min_var", "0.9", width=8)
        r += 1
        # Draft-model placement: without -ngld the draft model can land on CPU
        # and erase the speculative speedup. Blank = llama-server default.
        erow(r, "Draft NGL (-ngld):", "spec_ngld_var", "", width=8)
        r += 1
        crow(r, "Draft KV K (-ctkd):", "spec_ctkd_var", "", ["", "f16", "q8_0", "q4_0"], width=8)
        r += 1
        crow(r, "Draft KV V (-ctvd):", "spec_ctvd_var", "", ["", "f16", "q8_0", "q4_0"], width=8)
        r += 1

        # Sampling Parameters
        tk.Frame(outer, bg=BG4, height=1).grid(row=r, column=0, columnspan=2, sticky="ew", pady=6)
        r += 1
        tk.Label(outer, text="SAMPLING PARAMETERS", bg=BG, fg=ACCENT, font=("Segoe UI", 9, "bold")).grid(row=r, column=0, columnspan=2, sticky="w", padx=8, pady=(0,4))
        r += 1
        
        # Helper to create a parameter row with a checkbox
        def param_row_with_check(r, label_text, val_var_name, default_val, check_var_name, check_default=True):
            val_var = tk.StringVar(value=default_val)
            setattr(self, val_var_name, val_var)
            val_var.trace_add("write", self._schedule_update)
            
            check_var = tk.BooleanVar(value=check_default)
            setattr(self, check_var_name, check_var)
            
            tk.Label(outer, text=label_text, bg=BG, fg=FG, anchor="e", width=18).grid(row=r, column=0, padx=(8,4), pady=2, sticky="e")
            tk.Entry(outer, textvariable=val_var, bg=BG3, fg=FG, insertbackground=FG, relief="flat", bd=1, width=8).grid(row=r, column=1, padx=4, pady=2, sticky="w")
            tk.Checkbutton(outer, variable=check_var, bg=BG, fg=FG, selectcolor=BG3, command=self._schedule_update).grid(row=r, column=2, sticky="w", padx=(8,0))
            return r + 1

        r = param_row_with_check(r, "Temperature:", "srv_temp_var", "0.8", "enable_temp_var")
        r = param_row_with_check(r, "Top-K:", "srv_top_k_var", "40", "enable_top_k_var")
        r = param_row_with_check(r, "Top-P:", "srv_top_p_var", "0.9", "enable_top_p_var")
        r = param_row_with_check(r, "Min-P:", "srv_min_p_var", "0.1", "enable_min_p_var")
        r = param_row_with_check(r, "Repeat Penalty:", "srv_repeat_p_var", "1.1", "enable_repeat_p_var")
        r = param_row_with_check(r, "Repeat Last N:", "srv_repeat_last_var", "64", "enable_repeat_last_var")
        r = param_row_with_check(r, "Presence Penalty:", "srv_presence_p_var", "0.0", "enable_presence_p_var")
        r = param_row_with_check(r, "Frequency Penalty:", "srv_frequency_p_var", "0.0", "enable_frequency_p_var")
        r = param_row_with_check(r, "Typical P:", "srv_typical_var", "1.0", "enable_typical_var")
        # Modern samplers — off by default (checkbox unticked = flag not sent).
        r = param_row_with_check(r, "DRY Multiplier:", "srv_dry_mult_var", "0.8", "enable_dry_var", check_default=False)
        r = param_row_with_check(r, "XTC Probability:", "srv_xtc_p_var", "0.5", "enable_xtc_p_var", check_default=False)
        r = param_row_with_check(r, "XTC Threshold:", "srv_xtc_t_var", "0.1", "enable_xtc_t_var", check_default=False)
        r = param_row_with_check(r, "Top-NSigma:", "srv_top_nsigma_var", "1.0", "enable_top_nsigma_var", check_default=False)
        r += 1

        # Chat template / reasoning
        tk.Frame(outer, bg=BG4, height=1).grid(row=r, column=0, columnspan=2, sticky="ew", pady=6)
        r += 1
        tk.Label(outer, text="TEMPLATE / REASONING", bg=BG, fg=ACCENT, font=("Segoe UI", 9, "bold")).grid(row=r, column=0, columnspan=2, sticky="w", padx=8, pady=(0,4))
        r += 1
        crow(r, "Reasoning Fmt:", "reasoning_fmt_var", "", ["", "auto", "none", "deepseek"], width=10)
        r += 1
        erow(r, "Chat Template:", "chat_template_var", "", width=14)
        r += 1
        tk.Label(outer, text="Template File:", bg=BG, fg=FG, anchor="e", width=18).grid(row=r, column=0, padx=(8,4), pady=2, sticky="e")
        ctf = frame(outer)
        ctf.grid(row=r, column=1, sticky="ew", padx=4, pady=2)
        self.chat_template_file_var = tk.StringVar(value="")
        self.chat_template_file_var.trace_add("write", self._schedule_update)
        tk.Entry(ctf, textvariable=self.chat_template_file_var, bg=BG3, fg=FG, insertbackground=FG, relief="flat", bd=1, width=16).pack(side="left", fill="x", expand=True)
        ttk.Button(ctf, text="…", width=3, command=self._browse_chat_template).pack(side="left", padx=(2,0))
        r += 1

        # Checkboxes
        cf = frame(outer)
        cf.grid(row=r, column=0, columnspan=2, sticky="w", padx=8, pady=(4,8))
        self.flash_var = tk.BooleanVar(value=True)
        self.mlock_var = tk.BooleanVar(value=True)
        self.nommap_var = tk.BooleanVar(value=True)
        self.nowarm_var = tk.BooleanVar(value=False)
        checks = [("Flash Attention", self.flash_var), ("mlock", self.mlock_var), ("no-mmap", self.nommap_var), ("no-warmup", self.nowarm_var), ("Jinja", self.jinja_var)]
        for i, (txt, var) in enumerate(checks):
            tk.Checkbutton(cf, text=txt, variable=var, bg=BG, fg=FG, activebackground=BG, activeforeground=FG, selectcolor=BG3,
                          command=self._schedule_update).grid(row=i//2, column=i%2, sticky="w", padx=(0,12), pady=1)

    def _build_command_configs(self, parent, col):
        outer = tk.LabelFrame(parent, text="  GENERATED COMMAND  ", bg=BG, fg=FG, font=("Segoe UI", 9, "bold"), bd=1, relief="groove")
        outer.grid(row=0, column=col, sticky="nsew", padx=(3,0), pady=2)
        outer.columnconfigure(0, weight=1)

        self.cmd_text = dark_text(outer, height=7, wrap="word", font=("Consolas", 9), state="disabled")
        self.cmd_text.pack(fill="x", padx=6, pady=(6,4))

        tk.Button(outer, text="📋  Copy Command", bg=BG4, fg=ACCENT, relief="flat", bd=0, padx=8, pady=5, command=self._copy_cmd).pack(fill="x", padx=6, pady=(0,8))
        sep(outer, pady=2)

        tk.Label(outer, text="SAVED CONFIGS", bg=BG, fg=FG, font=("Segoe UI", 8, "bold")).pack(pady=(4,4))

        df = frame(outer)
        df.pack(fill="x", padx=6, pady=(0,4))
        df.columnconfigure(1, weight=1)
        tk.Label(df, text="Save to:", bg=BG, fg=FG2, font=("Segoe UI", 8)).grid(row=0, column=0, sticky="w", padx=(0,4))
        self.save_dir_lbl = tk.Label(df, text=str(self._cfg_dir), bg=BG2, fg=ACCENT, font=("Consolas", 8), anchor="w", relief="flat", padx=4)
        self.save_dir_lbl.grid(row=0, column=1, sticky="ew", padx=(0,4))
        tk.Button(df, text="📁 Change", bg=BG4, fg=FG2, relief="flat", bd=0, padx=6, pady=2, font=("Segoe UI", 8), command=self._change_save_dir).grid(row=0, column=2)

        nf = frame(outer)
        nf.pack(fill="x", padx=6, pady=2)
        nf.columnconfigure(0, weight=1)
        self.cfg_name_var = tk.StringVar(value="My Config")
        tk.Entry(nf, textvariable=self.cfg_name_var, bg=BG3, fg=FG, insertbackground=FG, relief="flat", bd=1).grid(row=0, column=0, sticky="ew", padx=(0,4))
        tk.Button(nf, text="💾 Save", bg=BG4, fg=FG, relief="flat", bd=0, padx=8, pady=3, command=self._save_cfg).grid(row=0, column=1)

        lf = frame(outer)
        lf.pack(fill="x", padx=6, pady=(2,2))
        lf.columnconfigure(0, weight=1)
        self.cfg_var = tk.StringVar()
        self.cfg_combo = ttk.Combobox(lf, textvariable=self.cfg_var, values=self._cfg_keys(), state="readonly")
        self.cfg_combo.grid(row=0, column=0, sticky="ew", padx=(0,4))
        self.cfg_combo.bind("<<ComboboxSelected>>", lambda e: self._load_cfg(self.cfg_var.get()))
        tk.Button(lf, text="🗑", bg=BG4, fg=RED, relief="flat", bd=0, padx=6, command=self._del_cfg).grid(row=0, column=1)

        tk.Button(outer, text="📂  Load Config File…", bg=BG4, fg=ACCENT, relief="flat", bd=0, padx=8, pady=3, font=("Segoe UI", 8), command=self._load_cfg_file).pack(fill="x", padx=6, pady=(2,2))

        tk.Label(outer, text="Notes:", bg=BG, fg=FG, font=("Segoe UI", 8)).pack(anchor="w", padx=6, pady=(6,2))
        self.notes_var = tk.StringVar()
        tk.Entry(outer, textvariable=self.notes_var, bg=BG3, fg=FG, insertbackground=FG, relief="flat", bd=1).pack(fill="x", padx=6, pady=(0,8))

    def _build_launch_log(self, parent):
        outer = tk.LabelFrame(parent, text="  SERVER  ", bg=BG, fg=FG, font=("Segoe UI", 9, "bold"), bd=1, relief="groove")
        outer.pack(fill="both", expand=True, padx=6, pady=(2,6))
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(2, weight=1)

        ctrl = frame(outer)
        ctrl.grid(row=0, column=0, sticky="ew", padx=6, pady=6)

        self.launch_btn = tk.Button(ctrl, text="▶  Launch Server", bg=GREEN2, fg=BG, activebackground=GREEN, activeforeground=BG,
                                   relief="flat", bd=0, padx=14, pady=6, font=("Segoe UI", 10, "bold"), command=self._launch)
        self.launch_btn.pack(side="left", padx=(0,6))

        self.stop_btn = tk.Button(ctrl, text="⏹  Stop", bg=RED2, fg=BG, activebackground=RED, activeforeground=BG,
                                 relief="flat", bd=0, padx=10, pady=6, font=("Segoe UI", 10, "bold"), state="disabled", command=self._stop)
        self.stop_btn.pack(side="left", padx=(0,20))

        tk.Label(ctrl, text="Speed:", bg=BG, fg=FG2).pack(side="left", padx=(0,4))
        self.speed_lbl = tk.Label(ctrl, text="—  tk/s", bg=BG, fg=GREEN, font=("Segoe UI", 14, "bold"))
        self.speed_lbl.pack(side="left", padx=(0,20))

        self.status_lbl = tk.Label(ctrl, text="●  Stopped", bg=BG, fg=FG2)
        self.status_lbl.pack(side="right", padx=10)
        tk.Button(ctrl, text="🗑 Clear", bg=BG4, fg=FG2, relief="flat", bd=0, padx=8, command=self._clear_log).pack(side="right")

        mem_row = frame(outer)
        mem_row.grid(row=1, column=0, sticky="ew", padx=6, pady=(0,2))
        mem_row.columnconfigure(2, weight=1)
        mem_row.columnconfigure(5, weight=1)
        mem_row.columnconfigure(8, weight=1)

        tk.Checkbutton(mem_row, text="Mem Monitor", variable=self._mem_enabled, bg=BG, fg=FG2, activebackground=BG, activeforeground=FG,
                      selectcolor=BG3, font=("Segoe UI", 8), command=self._on_mem_toggle).grid(row=0, column=0, padx=(0,4), sticky="w")

        tk.Label(mem_row, text="every", bg=BG, fg=FG2, font=("Segoe UI", 8)).grid(row=0, column=1, padx=(0,2))
        self.mem_interval_var = tk.StringVar(value="2s")
        iv = ttk.Combobox(mem_row, textvariable=self.mem_interval_var, values=["1s","2s","5s","10s"], width=4, state="readonly")
        iv.grid(row=0, column=2, padx=(0,12), sticky="w")
        iv.bind("<<ComboboxSelected>>", self._on_interval_change)

        tk.Label(mem_row, text="CPU:", bg=BG, fg=FG2, font=("Segoe UI", 8)).grid(row=0, column=3, padx=(0,4), sticky="w")
        self.cpu_bar_var = tk.DoubleVar(value=0)
        self.cpu_bar = ttk.Progressbar(mem_row, variable=self.cpu_bar_var, maximum=100, length=100)
        self.cpu_bar.grid(row=0, column=4, sticky="ew", padx=(0,4))
        self.cpu_lbl = tk.Label(mem_row, text="—%", bg=BG, fg=FG, font=("Consolas", 8), width=8, anchor="w")
        self.cpu_lbl.grid(row=0, column=5, padx=(0,12))

        tk.Label(mem_row, text="GPU VRAM:", bg=BG, fg=FG2, font=("Segoe UI", 8)).grid(row=0, column=6, padx=(0,4), sticky="w")
        self.gpu_bar_var = tk.DoubleVar(value=0)
        self.gpu_bar = ttk.Progressbar(mem_row, variable=self.gpu_bar_var, maximum=100, length=150)
        self.gpu_bar.grid(row=0, column=7, sticky="ew", padx=(0,4))
        self.gpu_mem_lbl = tk.Label(mem_row, text="— / — MiB", bg=BG, fg=ACCENT, font=("Consolas", 8), width=18, anchor="w")
        self.gpu_mem_lbl.grid(row=0, column=8, padx=(0,12))

        tk.Label(mem_row, text="RAM:", bg=BG, fg=FG2, font=("Segoe UI", 8)).grid(row=0, column=9, padx=(0,4), sticky="e")
        self.ram_bar_var = tk.DoubleVar(value=0)
        self.ram_bar = ttk.Progressbar(mem_row, variable=self.ram_bar_var, maximum=100, length=130)
        self.ram_bar.grid(row=0, column=10, sticky="ew", padx=(0,4))
        self.ram_mem_lbl = tk.Label(mem_row, text="— / — GB", bg=BG, fg=GOLD, font=("Consolas", 8), width=14, anchor="w")
        self.ram_mem_lbl.grid(row=0, column=11, padx=(0,4))

        log_frame = frame(outer)
        log_frame.grid(row=2, column=0, sticky="nsew", padx=6, pady=(0,6))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log = dark_text(log_frame, font=("Consolas", 9), wrap="none", state="disabled")
        self.log.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.log.configure(yscrollcommand=sb.set)

    def _build_test_tab(self, parent):
        parent.columnconfigure(0, weight=3)
        parent.columnconfigure(1, weight=2)
        parent.rowconfigure(0, weight=1)

        left = tk.LabelFrame(parent, text="  🧪  PROMPT & RESPONSE  ", bg=BG, fg=ACCENT, font=("Segoe UI", 9, "bold"), bd=1, relief="groove")
        left.grid(row=0, column=0, sticky="nsew", padx=(6,3), pady=6)
        left.columnconfigure(0, weight=1)
        left.rowconfigure(2, weight=1)

        ctrl = frame(left)
        ctrl.grid(row=0, column=0, sticky="ew", padx=6, pady=(6,4))

        tk.Label(ctrl, text="Max Tokens:", bg=BG, fg=FG2).pack(side="left", padx=(0,4))
        self.max_tok_var = tk.StringVar(value="300")
        tk.Entry(ctrl, textvariable=self.max_tok_var, bg=BG3, fg=FG, insertbackground=FG, relief="flat", bd=1, width=6).pack(side="left", padx=(0,10))

        tk.Label(ctrl, text="Temperature:", bg=BG, fg=FG2).pack(side="left", padx=(0,4))
        self.temp_var = tk.StringVar(value="1.0")
        tk.Entry(ctrl, textvariable=self.temp_var, bg=BG3, fg=FG, insertbackground=FG, relief="flat", bd=1, width=5).pack(side="left", padx=(0,10))

        self.send_btn = tk.Button(ctrl, text="▶  Send & Measure", bg="#1e3a5f", fg=ACCENT, activebackground="#162d4a", activeforeground=ACCENT,
                                 relief="flat", bd=0, padx=12, pady=5, font=("Segoe UI", 9, "bold"), command=self._send_prompt)
        self.send_btn.pack(side="right")
        tk.Button(ctrl, text="Clear", bg=BG4, fg=FG2, relief="flat", bd=0, padx=8, pady=5, command=self._clear_test).pack(side="right", padx=(0,6))

        tk.Label(left, text="Prompt:", bg=BG, fg=FG2, font=("Segoe UI", 8)).grid(row=1, column=0, sticky="w", padx=8, pady=(2,2))
        self.prompt_box = dark_text(left, height=5, wrap="word", font=("Segoe UI", 10))
        self.prompt_box.grid(row=1, column=0, sticky="ew", padx=6, pady=(0,4))
        self.prompt_box.insert("1.0", DEFAULT_PROMPT)

        tk.Label(left, text="Response:", bg=BG, fg=FG, font=("Segoe UI", 8, "bold")).grid(row=2, column=0, sticky="w", padx=8, pady=(4,2))
        resp_frame = frame(left)
        resp_frame.grid(row=2, column=0, sticky="nsew", padx=6, pady=(0,6))
        resp_frame.columnconfigure(0, weight=1)
        resp_frame.rowconfigure(0, weight=1)
        self.response_box = dark_text(resp_frame, wrap="word", font=("Consolas", 10))
        self.response_box.grid(row=0, column=0, sticky="nsew")
        rs = ttk.Scrollbar(resp_frame, orient="vertical", command=self.response_box.yview)
        rs.grid(row=0, column=1, sticky="ns")
        self.response_box.configure(yscrollcommand=rs.set)

        right = tk.LabelFrame(parent, text="  RESULTS  ", bg=BG, fg=ACCENT, font=("Segoe UI", 9, "bold"), bd=1, relief="groove")
        right.grid(row=0, column=1, sticky="nsew", padx=(3,6), pady=6)
        right.columnconfigure(0, weight=1)

        self.test_speed_lbl = tk.Label(right, text="—", bg=BG, fg=GREEN, font=("Segoe UI", 52, "bold"))
        self.test_speed_lbl.pack(pady=(20,0))
        tk.Label(right, text="tokens / second", bg=BG, fg=FG2, font=("Segoe UI", 10)).pack(pady=(0,10))

        sep(right)

        sf = frame(right)
        sf.pack(fill="x", padx=16)
        sf.columnconfigure(1, weight=1)
        self._stat_labels = {}
        stats = [("tokens_gen","Tokens Generated:"), ("time_elapsed","Time Elapsed:"), ("time_to_first","Time to First Token:"), ("prompt_tokens","Prompt Tokens:")]
        for i, (k, txt) in enumerate(stats):
            tk.Label(sf, text=txt, bg=BG, fg=FG2, font=("Segoe UI", 9)).grid(row=i, column=0, sticky="w", pady=3)
            v = tk.Label(sf, text="—", bg=BG, fg=FG, font=("Segoe UI", 9, "bold"))
            v.grid(row=i, column=1, sticky="e", pady=3)
            self._stat_labels[k] = v

        sep(right)

        tk.Label(right, text="Best This Session:", bg=BG, fg=FG2, font=("Segoe UI", 9)).pack()
        self.best_speed_lbl = tk.Label(right, text="—  tk/s", bg=BG, fg=GOLD, font=("Segoe UI", 16, "bold"))
        self.best_speed_lbl.pack(pady=(2,8))

        self.test_status_lbl = tk.Label(right, text="Launch server first,\nthen send a prompt", bg=BG, fg=FG2, font=("Segoe UI", 9), wraplength=200, justify="center")
        self.test_status_lbl.pack(pady=6)

    def _send_prompt(self):
        if self._test_running: return
        prompt = self.prompt_box.get("1.0","end").strip()
        if not prompt:
            messagebox.showwarning("Empty","Enter a prompt first."); return
        try: max_tokens = int(self.max_tok_var.get())
        except: max_tokens = 300
        try: temperature = float(self.temp_var.get())
        except: temperature = 1.0

        url = f"http://{self.host_var.get()}:{self.port_var.get()}/v1/chat/completions"
        # Ask llama-server for authoritative token timings so tk/s reflects real
        # generated tokens (not streamed-chunk count, which is wrong under MTP /
        # speculative decoding). timings_per_token streams a `timings` block;
        # include_usage adds usage.completion_tokens in the final chunk. Both are
        # harmless to servers that ignore unknown fields.
        payload = {"model":"local", "messages":[{"role":"user","content":prompt}],
                   "max_tokens":max_tokens, "temperature":temperature, "stream":True,
                   "timings_per_token": True, "stream_options": {"include_usage": True}}

        self.response_box.delete("1.0","end")
        self.test_speed_lbl.configure(text="…", fg=GOLD)
        self.test_status_lbl.configure(text=" Waiting for first token…", fg=GOLD)
        for v in self._stat_labels.values(): v.configure(text="…")
        self.send_btn.configure(state="disabled", text="⏳ Running…")
        self._test_running = True
        threading.Thread(target=self._run_test, args=(url,payload), daemon=True).start()

    def _run_test(self, url, payload):
        data = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type":"application/json"})
        # chunks = streamed-delta count (fallback only). t_first/t_last bound the
        # decode window for the fallback estimate. timings/usage hold the server's
        # authoritative numbers when available.
        chunks=0; prompt_tok=0; t_first=t_last=None; t_req=time.time()
        timings=None; usage_completion=None
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                for raw in resp:
                    line = raw.decode("utf-8","replace").strip()
                    if not line.startswith("data: "): continue
                    body = line[6:]
                    if body=="[DONE]": break
                    try: chunk=json.loads(body)
                    except: continue
                    usage=chunk.get("usage")
                    if usage:
                        prompt_tok=usage.get("prompt_tokens",prompt_tok) or prompt_tok
                        if usage.get("completion_tokens"):
                            usage_completion=usage.get("completion_tokens")
                    if chunk.get("timings"):
                        timings=chunk.get("timings")
                    choices=chunk.get("choices",[])
                    if not choices: continue
                    delta=choices[0].get("delta",{})
                    content=delta.get("content","") or delta.get("reasoning_content","")
                    if content:
                        now=time.time()
                        if t_first is None:
                            t_first=now
                            self.after(0,lambda: self.test_status_lbl.configure(text="🟢 Generating…", fg=GREEN))
                        t_last=now
                        chunks+=1
                        self.after(0,lambda c=content: self._append_response(c))
                        # Prefer the server's live token rate when it streams one;
                        # otherwise show a coarse chunk-based estimate.
                        live=None
                        if timings and timings.get("predicted_per_second"):
                            live=timings["predicted_per_second"]
                        elif chunks%5==0 and t_last>t_first:
                            live=(chunks-1)/(t_last-t_first)
                        if live is not None:
                            self.after(0,lambda s=live: self.test_speed_lbl.configure(text=f"{s:.1f}", fg=GREEN))
        except urllib.error.URLError as e:
            self.after(0,lambda: self._test_error(f"Cannot reach server.\nIs it running?\n{e}")); return
        except Exception as e:
            self.after(0,lambda: self._test_error(str(e))); return

        ttft=(t_first-t_req) if t_first else 0
        # Resolve the final numbers, preferring the server's own measurement.
        if timings and timings.get("predicted_per_second") is not None:
            tks=float(timings["predicted_per_second"])
            tokens=int(timings.get("predicted_n") or usage_completion or chunks)
            gen_time=(timings.get("predicted_ms") or 0)/1000.0
            source="server timings"
        elif usage_completion and t_first and t_last and t_last>t_first:
            tokens=int(usage_completion)
            gen_time=t_last-t_first
            tks=tokens/gen_time if gen_time>0 else 0
            source="server usage"
        else:
            # Last resort: chunk-count estimate. Count N tokens over the N-1
            # inter-token gaps to avoid over-counting the first token.
            tokens=chunks
            gen_time=(t_last-t_first) if (t_first and t_last) else 0
            tks=((chunks-1)/gen_time) if (gen_time>0 and chunks>1) else 0
            source="≈ estimated (no server timings)"
        self.after(0,lambda: self._show_results(tks,tokens,gen_time,ttft,prompt_tok,source))

    def _append_response(self, text):
        self.response_box.insert("end", text)
        self.response_box.see("end")

    def _show_results(self, tks, tokens, gen_time, ttft, prompt_tokens, source="server timings"):
        self._test_running=False
        self.send_btn.configure(state="normal", text="▶  Send & Measure")
        color = GREEN if tks>=15 else GOLD if tks>=8 else RED
        self.test_speed_lbl.configure(text=f"{tks:.1f}", fg=color)
        self._stat_labels["tokens_gen"].configure(text=f"{tokens:,} tokens")
        self._stat_labels["time_elapsed"].configure(text=f"{gen_time:.2f}s")
        self._stat_labels["time_to_first"].configure(text=f"{ttft*1000:.0f} ms" if ttft>0 else "—")
        self._stat_labels["prompt_tokens"].configure(text=str(prompt_tokens) if prompt_tokens else "—")
        if tks>self._best_tks:
            self._best_tks=tks
            self.best_speed_lbl.configure(text=f"{tks:.1f}  tk/s")
        self.test_status_lbl.configure(text=f"✅ Done — {tokens} tokens in {gen_time:.1f}s ({source})", fg=GREEN)
        self.speed_lbl.configure(text=f"{tks:.1f}  tk/s")
        self._log(f"[{self._ts()}] 🧪 {tks:.1f} tk/s ({tokens} tok, {gen_time:.1f}s, TTFT {ttft*1000:.0f}ms) [{source}]\n")

    def _test_error(self, msg):
        self._test_running=False
        self.send_btn.configure(state="normal", text="▶  Send & Measure")
        self.test_speed_lbl.configure(text="ERR", fg=RED)
        self.test_status_lbl.configure(text=f" {msg[:140]}", fg=RED)

    def _clear_test(self):
        self.response_box.delete("1.0","end")
        self.test_speed_lbl.configure(text="—", fg=GREEN)
        for v in self._stat_labels.values(): v.configure(text="—")
        self.test_status_lbl.configure(text="Ready", fg=FG2)

    def _exe_path(self):
        return str(Path(self.llama_dir_var.get()) / "llama-server.exe")

    def _model_path(self):
        return str(Path(self.models_dir_var.get()) / self.model_var.get())

    def _build_args(self):
        a=["-m",self._model_path(),"-ngl",self.ngl_var.get()]
        moe=self.moe_var.get().strip()
        if moe and moe!="0": a+=["--n-cpu-moe",moe]
        if self.nommap_var.get(): a.append("--no-mmap")
        a+=["-ctk",self.ctk_var.get(),"-ctv",self.ctv_var.get()]
        if self.flash_var.get(): a+=["--flash-attn","on"]
        if self.mlock_var.get(): a.append("--mlock")
        if self.nowarm_var.get(): a.append("--no-warmup")
        a+=["-c",self.ctx_var.get()]
        for val,flag in [(self.threads_var.get(),"-t"),(self.batch_var.get(),"-b"), (self.ubatch_var.get(),"-ub"),(self.np_var.get(),"-np")]:
            if val.strip(): a+=[flag,val.strip()]
        sel=self._selected_gpus()
        ts=self.ts_var.get().strip() if hasattr(self,"ts_var") else ""
        if len(sel)>=2 and ts: a+=["-ts",ts]

        # ---- Auto-fit ----
        if hasattr(self, "fit_var") and self.fit_var.get():
            a += ["-fit", self.fit_var.get()]
        if hasattr(self, "fit_target_var") and self.fit_target_var.get().strip():
            a += ["-fitt", self.fit_target_var.get().strip()]
        if hasattr(self, "fit_ctx_var") and self.fit_ctx_var.get().strip():
            a += ["-fitc", self.fit_ctx_var.get().strip()]

        # ---- Multi-GPU placement ----
        if hasattr(self, "split_mode_var") and self.split_mode_var.get() and self.split_mode_var.get() != "none":
            a += ["-sm", self.split_mode_var.get()]
        if hasattr(self, "main_gpu_var") and self.main_gpu_var.get().strip():
            a += ["-mg", self.main_gpu_var.get().strip()]
        if hasattr(self, "override_tensor_var") and self.override_tensor_var.get().strip():
            a += ["-ot", self.override_tensor_var.get().strip()]

        # ---- NUMA / CPU affinity / repack ----
        if hasattr(self, "numa_var") and self.numa_var.get().strip():
            a += ["--numa", self.numa_var.get().strip()]
        if hasattr(self, "cpu_range_var") and self.cpu_range_var.get().strip():
            a += ["-Cr", self.cpu_range_var.get().strip()]
        if hasattr(self, "repack_choice_var") and self.repack_choice_var.get() == "off":
            a.append("--no-repack")
        
        cache_reuse = self.srv_cache_reuse_var.get().strip()
        if cache_reuse and cache_reuse != "0": a += ["--cache-reuse", cache_reuse]
        
        # Sampling parameters (only added if enabled)
        if self.enable_temp_var.get():
            temp = self.srv_temp_var.get().strip()
            if temp: a += ["--temp", temp]
            
        if self.enable_top_k_var.get():
            top_k = self.srv_top_k_var.get().strip()
            if top_k: a += ["--top-k", top_k]
            
        if self.enable_top_p_var.get():
            top_p = self.srv_top_p_var.get().strip()
            if top_p: a += ["--top-p", top_p]
            
        if self.enable_min_p_var.get():
            min_p = self.srv_min_p_var.get().strip()
            if min_p: a += ["--min-p", min_p]
            
        if self.enable_repeat_p_var.get():
            repeat_p = self.srv_repeat_p_var.get().strip()
            if repeat_p: a += ["--repeat-penalty", repeat_p]
            
        if self.enable_repeat_last_var.get():
            repeat_last = self.srv_repeat_last_var.get().strip()
            if repeat_last: a += ["--repeat-last-n", repeat_last]  # fixed flag
            
        if self.enable_presence_p_var.get():
            presence_p = self.srv_presence_p_var.get().strip()
            if presence_p: a += ["--presence-penalty", presence_p]
            
        if self.enable_frequency_p_var.get():
            frequency_p = self.srv_frequency_p_var.get().strip()
            if frequency_p: a += ["--frequency-penalty", frequency_p]
            
        if self.enable_typical_var.get():
            typical = self.srv_typical_var.get().strip()
            if typical: a += ["--typical", typical]

        if self.enable_dry_var.get():
            v = self.srv_dry_mult_var.get().strip()
            if v: a += ["--dry-multiplier", v]
        if self.enable_xtc_p_var.get():
            v = self.srv_xtc_p_var.get().strip()
            if v: a += ["--xtc-probability", v]
        if self.enable_xtc_t_var.get():
            v = self.srv_xtc_t_var.get().strip()
            if v: a += ["--xtc-threshold", v]
        if self.enable_top_nsigma_var.get():
            v = self.srv_top_nsigma_var.get().strip()
            if v: a += ["--top-nsigma", v]

        # ---- MTP (Multi-Token Prediction) ----
        # The old --draft flag is removed; use --spec-type draft-mtp and --spec-draft-n-max
        mtp = self.mtp_var.get().strip()
        if mtp and mtp != "0":
            a += ["--spec-type", "draft-mtp"]
            a += ["--spec-draft-n-max", mtp]
            # --spec-draft-p-min filters low-confidence draft tokens and matters
            # for MTP too, not just classic speculative decoding — don't drop it
            # just because MTP is the active mode.
            p_min = self.spec_draft_p_min_var.get().strip()
            if p_min:
                a += ["--spec-draft-p-min", p_min]
            mtp_handled = True
        else:
            mtp_handled = False
        
        # ---- Speculative decoding (classic draft-model / n-gram) ----
        # Only add if MTP was not already set (to avoid conflicting --spec-type)
        if not mtp_handled:
            spec_type = self.spec_type_var.get()
            if spec_type and spec_type != "none":
                a += ["--spec-type", spec_type]
                draft_model = self.spec_draft_model_var.get().strip()
                if draft_model:
                    a += ["--model-draft", draft_model]
                    # Draft-model placement (only meaningful with a draft model)
                    ngld = self.spec_ngld_var.get().strip()
                    if ngld:
                        a += ["-ngld", ngld]
                    ctkd = self.spec_ctkd_var.get().strip()
                    if ctkd:
                        a += ["-ctkd", ctkd]
                    ctvd = self.spec_ctvd_var.get().strip()
                    if ctvd:
                        a += ["-ctvd", ctvd]
                n_max = self.spec_draft_n_max_var.get().strip()
                if n_max:
                    a += ["--spec-draft-n-max", n_max]
                p_min = self.spec_draft_p_min_var.get().strip()
                if p_min:
                    a += ["--spec-draft-p-min", p_min]

        if self.jinja_var.get(): a.append("--jinja")
        rf = self.reasoning_fmt_var.get().strip()
        if rf: a += ["--reasoning-format", rf]
        ct = self.chat_template_var.get().strip()
        ctf = self.chat_template_file_var.get().strip()
        if ctf:
            a += ["--chat-template-file", ctf]
        elif ct:
            a += ["--chat-template", ct]
        a+=["--host",self.host_var.get(),"--port",self.port_var.get()]
        return a

    def _cuda_env(self):
        s=self._selected_gpus(); return ",".join(s) if s else "0"

    def _ps_command(self):
        # Quote any arg PowerShell would split or reparse (spaces, ; , ( ) etc.)
        # — model paths with spaces and -ot regexes broke the copied command.
        def q(arg):
            return f'"{arg}"' if re.search(r'[\s;,()\[\]{}&|<>\'"]', arg) else arg
        args = " ".join(q(a) for a in self._build_args())
        return f'$env:CUDA_VISIBLE_DEVICES={self._cuda_env()}; & "{self._exe_path()}" {args}'

    def _copy_cmd(self):
        self.clipboard_clear(); self.clipboard_append(self._ps_command())
        self._log("📋 Command copied.\n")

    def _load_configs(self):
        try:
            cf = self._configs_file()
            if cf.exists(): self.saved_configs = json.loads(cf.read_text())
        except Exception as e:
            self.saved_configs = {}
            print(f"⚠ Could not read configs file: {e}", file=sys.stderr)

    def _cfg_dict(self):
        return {"llama_dir":self.llama_dir_var.get(),"models_dir":self.models_dir_var.get(), "model":self.model_var.get(),"ngl":self.ngl_var.get(),"moe":self.moe_var.get(),
                "ctk":self.ctk_var.get(),"ctv":self.ctv_var.get(),"ctx":self.ctx_var.get(), "threads":self.threads_var.get(),"batch":self.batch_var.get(),
                "ubatch":self.ubatch_var.get(),"np":self.np_var.get(), "host":self.host_var.get(),"port":self.port_var.get(),
                "selected_gpus":self._selected_gpus(), "ts":self.ts_var.get() if hasattr(self,"ts_var") else "",
                "flash":self.flash_var.get(),"mlock":self.mlock_var.get(), "nommap":self.nommap_var.get(),"nowarm":self.nowarm_var.get(),
                "notes":self.notes_var.get(), "spec_type":self.spec_type_var.get(),"spec_draft_model":self.spec_draft_model_var.get(),
                "spec_draft_n_max":self.spec_draft_n_max_var.get(),"spec_draft_p_min":self.spec_draft_p_min_var.get(),
                "jinja":self.jinja_var.get(), "mtp":self.mtp_var.get(), "srv_cache_reuse":self.srv_cache_reuse_var.get(),
                "srv_temp":self.srv_temp_var.get(),"srv_top_k":self.srv_top_k_var.get(), "srv_top_p":self.srv_top_p_var.get(),"srv_min_p":self.srv_min_p_var.get(),
                "srv_repeat_p":self.srv_repeat_p_var.get(),"srv_repeat_last":self.srv_repeat_last_var.get(),
                "srv_presence_p":self.srv_presence_p_var.get(),"srv_frequency_p":self.srv_frequency_p_var.get(), "srv_typical":self.srv_typical_var.get(),
                # Save checkbox states
                "enable_temp":self.enable_temp_var.get(), "enable_top_k":self.enable_top_k_var.get(), "enable_top_p":self.enable_top_p_var.get(),
                "enable_min_p":self.enable_min_p_var.get(), "enable_repeat_p":self.enable_repeat_p_var.get(), "enable_repeat_last":self.enable_repeat_last_var.get(),
                "enable_presence_p":self.enable_presence_p_var.get(), "enable_frequency_p":self.enable_frequency_p_var.get(), "enable_typical":self.enable_typical_var.get(),
                # GPU / CPU / Auto-Fit (added with the multi-build / TurboQuant pass)
                "fit":self.fit_var.get(), "fit_target":self.fit_target_var.get(), "fit_ctx":self.fit_ctx_var.get(),
                "split_mode":self.split_mode_var.get(), "main_gpu":self.main_gpu_var.get(), "override_tensor":self.override_tensor_var.get(),
                "numa":self.numa_var.get(), "cpu_range":self.cpu_range_var.get(), "repack_choice":self.repack_choice_var.get(),
                # Draft-model placement
                "spec_ngld":self.spec_ngld_var.get(), "spec_ctkd":self.spec_ctkd_var.get(), "spec_ctvd":self.spec_ctvd_var.get(),
                # Modern samplers
                "srv_dry_mult":self.srv_dry_mult_var.get(), "enable_dry":self.enable_dry_var.get(),
                "srv_xtc_p":self.srv_xtc_p_var.get(), "enable_xtc_p":self.enable_xtc_p_var.get(),
                "srv_xtc_t":self.srv_xtc_t_var.get(), "enable_xtc_t":self.enable_xtc_t_var.get(),
                "srv_top_nsigma":self.srv_top_nsigma_var.get(), "enable_top_nsigma":self.enable_top_nsigma_var.get(),
                # Template / reasoning
                "reasoning_fmt":self.reasoning_fmt_var.get(), "chat_template":self.chat_template_var.get(),
                "chat_template_file":self.chat_template_file_var.get()}

    def _apply_cfg(self,cfg):
        self.llama_dir_var.set(cfg.get("llama_dir",self.llama_dir_var.get()))
        self.models_dir_var.set(cfg.get("models_dir",self.models_dir_var.get()))
        self.ngl_var.set(cfg.get("ngl","999")); self.moe_var.set(cfg.get("moe","25"))
        self.ctk_var.set(cfg.get("ctk","f16")); self.ctv_var.set(cfg.get("ctv","f16"))
        self.ctx_var.set(cfg.get("ctx","258944")); self.threads_var.set(cfg.get("threads",""))
        self.batch_var.set(cfg.get("batch","")); self.ubatch_var.set(cfg.get("ubatch",""))
        self.np_var.set(cfg.get("np","")); self.host_var.set(cfg.get("host","127.0.0.1"))
        self.port_var.set(cfg.get("port","8080"))
        self.flash_var.set(cfg.get("flash",True)); self.mlock_var.set(cfg.get("mlock",True))
        self.nommap_var.set(cfg.get("nommap",True)); self.nowarm_var.set(cfg.get("nowarm",False))
        self.notes_var.set(cfg.get("notes",""))
        if hasattr(self,"ts_var"): self.ts_var.set(cfg.get("ts",""))
        self.spec_type_var.set(cfg.get("spec_type", "none"))
        self.spec_draft_model_var.set(cfg.get("spec_draft_model", ""))
        self.spec_draft_n_max_var.set(cfg.get("spec_draft_n_max", "3"))
        self.spec_draft_p_min_var.set(cfg.get("spec_draft_p_min", "0.9"))
        self.jinja_var.set(cfg.get("jinja", False))
        self.mtp_var.set(cfg.get("mtp", "0"))
        self.srv_cache_reuse_var.set(cfg.get("srv_cache_reuse", "0"))
        self.srv_temp_var.set(cfg.get("srv_temp", "0.8"))
        self.srv_top_k_var.set(cfg.get("srv_top_k", "40"))
        self.srv_top_p_var.set(cfg.get("srv_top_p", "0.9"))
        self.srv_min_p_var.set(cfg.get("srv_min_p", "0.1"))
        self.srv_repeat_p_var.set(cfg.get("srv_repeat_p", "1.1"))
        self.srv_repeat_last_var.set(cfg.get("srv_repeat_last", "64"))
        self.srv_presence_p_var.set(cfg.get("srv_presence_p", "0.0"))
        self.srv_frequency_p_var.set(cfg.get("srv_frequency_p", "0.0"))
        self.srv_typical_var.set(cfg.get("srv_typical", "1.0"))
        
        # Load checkbox states
        self.enable_temp_var.set(cfg.get("enable_temp", True))
        self.enable_top_k_var.set(cfg.get("enable_top_k", True))
        self.enable_top_p_var.set(cfg.get("enable_top_p", True))
        self.enable_min_p_var.set(cfg.get("enable_min_p", True))
        self.enable_repeat_p_var.set(cfg.get("enable_repeat_p", True))
        self.enable_repeat_last_var.set(cfg.get("enable_repeat_last", True))
        self.enable_presence_p_var.set(cfg.get("enable_presence_p", True))
        self.enable_frequency_p_var.set(cfg.get("enable_frequency_p", True))
        self.enable_typical_var.set(cfg.get("enable_typical", True))

        # GPU / CPU / Auto-Fit
        self.fit_var.set(cfg.get("fit", "on"))
        self.fit_target_var.set(cfg.get("fit_target", ""))
        self.fit_ctx_var.set(cfg.get("fit_ctx", ""))
        self.split_mode_var.set(cfg.get("split_mode", "layer"))
        self.main_gpu_var.set(cfg.get("main_gpu", "0"))
        self.override_tensor_var.set(cfg.get("override_tensor", ""))
        self.numa_var.set(cfg.get("numa", ""))
        self.cpu_range_var.set(cfg.get("cpu_range", ""))
        self.repack_choice_var.set(cfg.get("repack_choice", "on"))

        # Draft-model placement
        self.spec_ngld_var.set(cfg.get("spec_ngld", ""))
        self.spec_ctkd_var.set(cfg.get("spec_ctkd", ""))
        self.spec_ctvd_var.set(cfg.get("spec_ctvd", ""))
        # Modern samplers
        self.srv_dry_mult_var.set(cfg.get("srv_dry_mult", "0.8"))
        self.enable_dry_var.set(cfg.get("enable_dry", False))
        self.srv_xtc_p_var.set(cfg.get("srv_xtc_p", "0.5"))
        self.enable_xtc_p_var.set(cfg.get("enable_xtc_p", False))
        self.srv_xtc_t_var.set(cfg.get("srv_xtc_t", "0.1"))
        self.enable_xtc_t_var.set(cfg.get("enable_xtc_t", False))
        self.srv_top_nsigma_var.set(cfg.get("srv_top_nsigma", "1.0"))
        self.enable_top_nsigma_var.set(cfg.get("enable_top_nsigma", False))
        # Template / reasoning
        self.reasoning_fmt_var.set(cfg.get("reasoning_fmt", ""))
        self.chat_template_var.set(cfg.get("chat_template", ""))
        self.chat_template_file_var.set(cfg.get("chat_template_file", ""))
        
        try: self.moe_slider.set(int(self.moe_var.get()))
        except: pass
        saved=cfg.get("selected_gpus",[])
        for idx,var in self.gpu_vars.items(): var.set(idx in saved)
        self._update_ts_visibility()
        self._scan_models()
        sm=cfg.get("model","")
        if sm and sm in (self.model_combo["values"] or []):
            self.model_var.set(sm)
            self._refresh_model_card()
        elif sm:
            self._log(f"⚠ Config requested model '{sm}' but it wasn't found in {self.models_dir_var.get()} — kept current selection.\n")
        self._update_command()

    def _cfg_keys(self):
        return list(self.saved_configs.keys()) or ["(no saved configs)"]

    def _save_cfg(self):
        name=self.cfg_name_var.get().strip()
        if not name: messagebox.showwarning("Name required","Enter a name."); return
        if name in self.saved_configs:
            if not messagebox.askyesno("Overwrite?", f"A config named '{name}' already exists. Overwrite it?"):
                return
        self.saved_configs[name]=self._cfg_dict()
        _atomic_write_json(self._configs_file(), self.saved_configs)
        self.cfg_combo["values"]=self._cfg_keys(); self.cfg_var.set(name)
        self._log(f"💾 Saved '{name}' → {self._cfg_dir}\n")

    def _load_cfg(self, name):
        if name in self.saved_configs: self._apply_cfg(self.saved_configs[name])

    def _load_cfg_file(self):
        path = filedialog.askopenfilename(title="Load Config File", filetypes=[("JSON config files", "*.json"), ("All files", "*.*")], initialdir=str(self._cfg_dir))
        if not path: return
        try: imported = json.loads(Path(path).read_text())
        except Exception as e:
            messagebox.showerror("Load failed", "Could not read file: " + str(e)); return
        if not isinstance(imported, dict):
            messagebox.showerror("Load failed", "Not a valid config file."); return
        added = 0
        for name, cfg in list(imported.items()):
            if not isinstance(cfg, dict): continue
            if name in self.saved_configs:
                if not messagebox.askyesno("Overwrite?", "Config already exists: " + name + ". Overwrite?"): continue
            self.saved_configs[name] = cfg
            added += 1
        if added:
            _atomic_write_json(self._configs_file(), self.saved_configs)
            self.cfg_combo["values"] = self._cfg_keys()
            self._log("[" + self._ts() + "] Loaded " + str(added) + " config(s) from " + str(path) + "\n")
            messagebox.showinfo("Loaded", "Imported " + str(added) + " config(s). Now in dropdown.")
        else:
            self._log("[" + self._ts() + "] No new configs imported.\n")

    def _del_cfg(self):
        name=self.cfg_var.get()
        if name in self.saved_configs:
            if not messagebox.askyesno("Delete config?", f"Delete saved config '{name}'? This cannot be undone."):
                return
            del self.saved_configs[name]
            _atomic_write_json(self._configs_file(), self.saved_configs)
            self.cfg_combo["values"]=self._cfg_keys()
            self.cfg_var.set("")
            self._log(f"[{self._ts()}] 🗑 Deleted config '{name}'\n")

    def _set_cfg_dir(self, new_dir: Path):
        """Single source of truth for changing the config/save directory.
        Both 'Change' buttons (Setup panel and Generated Command panel) route
        through here so the two directory labels can never drift out of sync —
        previously each button only updated its own label, so changing the dir
        from one panel silently left the other panel showing the old path."""
        new_dir.mkdir(parents=True, exist_ok=True)
        self._cfg_dir = new_dir
        _save_bootstrap(new_dir)
        self._load_configs()
        self.cfg_combo["values"] = self._cfg_keys()
        if hasattr(self, "cfg_dir_lbl"): self.cfg_dir_lbl.configure(text=str(new_dir))
        if hasattr(self, "save_dir_lbl"): self.save_dir_lbl.configure(text=str(new_dir))
        self._log(f"[{self._ts()}] 📁 Config dir → {new_dir}\n")

    def _change_cfg_dir(self):
        d = filedialog.askdirectory(title="Select Config Directory")
        if not d: return
        self._set_cfg_dir(Path(d.replace("/", "\\")))

    def _change_save_dir(self):
        d = filedialog.askdirectory(title="Select folder to save configs", initialdir=str(self._cfg_dir))
        if not d: return
        self._set_cfg_dir(Path(d.replace("/", "\\")))

    def _apply_dirs(self):
        self._save_settings(); self._scan_models()
        self._refresh_model_card()
        self._log(f"[{self._ts()}] ✔ Directories saved.\n")

    def _browse_dir(self,var):
        d=filedialog.askdirectory()
        if d: var.set(d.replace("/","\\"))

    def _browse_chat_template(self):
        f = filedialog.askopenfilename(title="Select Chat Template (Jinja)",
                                        filetypes=[("Jinja templates", "*.jinja"), ("All files", "*.*")])
        if f:
            self.chat_template_file_var.set(f.replace("/", "\\"))

    def _browse_draft_model(self):
        initial = self.models_dir_var.get() if hasattr(self, "models_dir_var") else None
        f = filedialog.askopenfilename(title="Select Draft Model (GGUF)",
                                        filetypes=[("GGUF models", "*.gguf"), ("All files", "*.*")],
                                        initialdir=initial)
        if f:
            self.spec_draft_model_var.set(f.replace("/", "\\"))

    def _launch(self):
        if self.process: return
        if not self._selected_gpus():
            messagebox.showwarning("No GPU","Select at least one GPU."); return
        exe=self._exe_path()
        if not os.path.exists(exe):
            messagebox.showerror("Not found",f"llama-server.exe not found:\n{exe}"); return
        if not os.path.exists(self._model_path()):
            messagebox.showerror("Not found",f"Model not found:\n{self._model_path()}"); return
        cmd=[exe]+self._build_args()
        env=os.environ.copy(); env["CUDA_VISIBLE_DEVICES"]=self._cuda_env()
        self._log(f"[{self._ts()}] ▶ Launching (GPU {self._cuda_env()})…\n")
        self._log("CMD: "+" ".join(cmd)+"\n\n")
        flags=subprocess.CREATE_NO_WINDOW if sys.platform=="win32" else 0
        try:
            self.process=subprocess.Popen(cmd,stdout=subprocess.PIPE, stderr=subprocess.STDOUT,env=env,text=True,bufsize=1,creationflags=flags)
        except Exception as e:
            messagebox.showerror("Launch error",str(e)); return
        self.launch_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.status_lbl.configure(text="●  Running", fg=GREEN)
        threading.Thread(target=self._monitor, daemon=True).start()
        self._start_mem_poll()

    def _monitor(self):
        """
        Monitor server output and update speed label.
        Uses a very comprehensive regex to capture any line containing a speed value.
        """
        # Patterns to match:
        # - "12.34 tk/s", "12.34 t/s", "12.34 tokens per second", "12.34 tps"
        # - "eval time =  123.45 ms /  456.78 tokens per second"
        spd_pattern = re.compile(r"""
            (?:eval\s+time\s*=.*?/)?      # optional "eval time = ... /"
            \s*(\d+\.?\d*)\s*             # the numeric speed
            (?:tk/s|t/s|tokens\s+per\s+second|tps)
        """, re.IGNORECASE | re.VERBOSE)

        for line in self.process.stdout:
            self.after(0, lambda l=line: self._append_log(l))
            m = spd_pattern.search(line)
            if m:
                speed = m.group(1)
                self.after(0, lambda v=speed: self.speed_lbl.configure(text=f"{v}  tk/s"))

        self.process.wait()
        self.process = None
        self.after(0, self._stopped)

    def _stopped(self):
        self.launch_btn.configure(state="normal"); self.stop_btn.configure(state="disabled")
        self.status_lbl.configure(text="●  Stopped", fg=FG2)
        self.speed_lbl.configure(text="—  tk/s")
        self._stop_mem_poll()
        self._log(f"\n[{self._ts()}] ⏹ Stopped.\n")

    def _stop(self):
        if self.process: self.process.terminate()

    def _log(self,text):
        self.after(0,lambda: self._append_log(text))

    def _append_log(self,text):
        self.log.configure(state="normal")
        self.log.insert("end",text); self.log.see("end")
        self.log.configure(state="disabled")

    def _clear_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0","end")
        self.log.configure(state="disabled")

    def _ts(self): return datetime.now().strftime("%H:%M:%S")

    def _on_mem_toggle(self):
        if self._mem_enabled.get():
            if self.process: self._start_mem_poll()
        else: self._stop_mem_poll()

    def _on_interval_change(self, *_):
        mapping = {'1s': 1000, '2s': 2000, '5s': 5000, '10s': 10000}
        self._mem_interval = mapping.get(self.mem_interval_var.get(), 2000)
        if self._mem_poll_id and self.process:
            self._stop_mem_poll()
            self._start_mem_poll()

    def _start_mem_poll(self):
        self._stop_mem_poll()
        if self._mem_enabled.get(): self._poll_memory()

    def _stop_mem_poll(self):
        if self._mem_poll_id:
            self.after_cancel(self._mem_poll_id)
            self._mem_poll_id = None
        self.cpu_bar_var.set(0)
        self.gpu_bar_var.set(0)
        self.ram_bar_var.set(0)
        self.cpu_lbl.configure(text="—%")
        self.gpu_mem_lbl.configure(text="— / — MiB")
        self.ram_mem_lbl.configure(text="— / — GB")

    def _poll_memory(self):
        if not self._mem_enabled.get(): return
        threading.Thread(target=self._fetch_memory, daemon=True).start()
        self._mem_poll_id = self.after(self._mem_interval, self._poll_memory)

    def _fetch_memory(self):
        gpu_used = gpu_total = 0
        no_win = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        try:
            r = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=5, creationflags=no_win)
            sel = self._selected_gpus()
            lines = r.stdout.strip().splitlines()
            for idx in sel:
                i = int(idx)
                if i < len(lines):
                    parts = lines[i].split(",")
                    if len(parts) == 2:
                        gpu_used += int(parts[0].strip())
                        gpu_total += int(parts[1].strip())
        except Exception: pass

        ram_used = ram_total = 0.0
        cpu_percent = 0.0
        if HAS_PSUTIL:
            try:
                vm = psutil.virtual_memory()
                ram_used = vm.used / (1024**3)
                ram_total = vm.total / (1024**3)
                cpu_percent = psutil.cpu_percent(interval=0.5)
            except Exception: pass
        else:
            try:
                r = subprocess.run(["wmic", "OS", "get", "FreePhysicalMemory,TotalVisibleMemorySize", "/value"],
                                 capture_output=True, text=True, timeout=5, creationflags=no_win)
                vals = {}
                for line in r.stdout.splitlines():
                    if "=" in line:
                        k, v = line.strip().split("=", 1)
                        if v.strip().isdigit(): vals[k.strip()] = int(v.strip())
                if "TotalVisibleMemorySize" in vals and "FreePhysicalMemory" in vals:
                    total_kb = vals["TotalVisibleMemorySize"]
                    free_kb = vals["FreePhysicalMemory"]
                    ram_total = total_kb / (1024**2)
                    ram_used = (total_kb - free_kb) / (1024**2)
            except Exception: pass

        self.after(0, lambda: self._update_mem_ui(cpu_percent, gpu_used, gpu_total, ram_used, ram_total))

    def _update_mem_ui(self, cpu_percent, gpu_used, gpu_total, ram_used, ram_total):
        if cpu_percent > 0:
            self.cpu_bar_var.set(cpu_percent)
            style = "cyan.Horizontal.TProgressbar" if cpu_percent < 70 else ("orange.Horizontal.TProgressbar" if cpu_percent < 90 else "red.Horizontal.TProgressbar")
            self.cpu_bar.configure(style=style)
            self.cpu_lbl.configure(text=f"{cpu_percent:.0f}%")
        if gpu_total > 0:
            pct = (gpu_used / gpu_total) * 100
            self.gpu_bar_var.set(pct)
            style = "green.Horizontal.TProgressbar" if pct < 70 else ("orange.Horizontal.TProgressbar" if pct < 90 else "red.Horizontal.TProgressbar")
            self.gpu_bar.configure(style=style)
            self.gpu_mem_lbl.configure(text=f"{gpu_used:,} / {gpu_total:,} MiB")
        if ram_total > 0:
            pct = (ram_used / ram_total) * 100
            self.ram_bar_var.set(pct)
            style = "gold.Horizontal.TProgressbar" if pct < 80 else "red.Horizontal.TProgressbar"
            self.ram_bar.configure(style=style)
            self.ram_mem_lbl.configure(text=f"{ram_used:.1f} / {ram_total:.1f} GB")

    def on_close(self):
        self._stop_mem_poll()
        if self.process:
            self.process.terminate()
            try: self.process.wait(timeout=3)
            except subprocess.TimeoutExpired: self.process.kill()
        self.destroy()


if __name__=="__main__":
    app=LlamaLauncher()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()
