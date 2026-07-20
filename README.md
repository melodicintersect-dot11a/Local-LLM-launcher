<img width="1383" height="1016" alt="launcher-02" src="https://github.com/user-attachments/assets/901ed0c7-a81b-4e8d-a7ec-8a451133d177" />
<img width="1385" height="1019" alt="launcher-01" src="https://github.com/user-attachments/assets/1958ffc2-682e-4e53-822b-96efee373223" />
# 🦙 LLaMA Server Launcher

A pure Python / Tkinter GUI for launching and managing `llama-server.exe` from [llama.cpp](https://github.com/ggerganov/llama.cpp). 

Designed for power users who need deep control over sampling, speculative decoding, multi-GPU splitting, and VRAM auto-fitting, wrapped in a sleek, dark-mode interface.

![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey?logo=windows)
![License](https://img.shields.io/badge/License-MIT-green)

## ✨ Features

- **🎨 Sleek Dark UI:** Pure black/white theme with custom Tkinter styling. No phantom windows, proper vertical scrolling, and responsive resizing.
- **📖 Smart Model Cards:** Automatically parses `README.md` (YAML frontmatter), `config.json`, or HuggingFace Hub metadata to display model architecture, context limits, and capabilities.
- **🚀 Advanced Execution:** Full support for **Multi-Token Prediction (MTP)**, **Speculative Decoding** (Eagle3, N-gram, Draft models), and modern samplers (DRY, XTC, Top-NSigma).
- **💾 VRAM & Memory Management:** Auto-detects NVIDIA GPUs, calculates Tensor Splits (`-ts`), and features an Auto-Fit (`-fit`) UI for llama.cpp's native VRAM-fitting logic.
- **📊 Live Monitoring:** Real-time CPU, RAM, and GPU VRAM usage progress bars.
- **🧪 Built-in Benchmarking:** "Test Prompt" tab to send requests, measure Time-To-First-Token (TTFT), and calculate accurate Tokens/Second using server-side timings.
- **⚙️ Configuration Management:** Save, load, and export complex server configurations to JSON.
- - **🔄 Dual Compatibility:** Works seamlessly with both [mainline llama.cpp](https://github.com/ggml-org/llama.cpp) and the [TurboQuant fork](https://github.com/TheTom/llama-cpp-turboquant), including exclusive support for `turbo2/3/4` KV cache types.

## 📋 Prerequisites

1. **Python 3.10+** installed on your system.
2. **`llama-server.exe`**: Download the latest release from either:
   - [Mainline llama.cpp releases](https://github.com/ggml-org/llama.cpp/releases) *(Recommended for most users)*
   - [TurboQuant fork releases](https://github.com/TheTom/llama-cpp-turboquant) *(Required if you want to use `turbo2/3/4` KV cache quantization)*
3. **GGUF Models**: Place your `.gguf` models in a designated folder.

## 🛠️ Installation

1. Clone or download this repository:
   ```bash
   git clone https://github.com/YOUR_USERNAME/llama-server-launcher.git
   cd llama-server-launcher

### 📦 Dependencies & Running

The launcher is built with pure Python and **requires no mandatory dependencies** to run. However, installing the optional dependencies unlocks live system monitoring and rich model card parsing.

**1. Install Optional Dependencies (Recommended):**
```bash
pip install psutil huggingface_hub pyyaml

## ⚠️ Compatibility & Pro-Tips

- **Mainline vs. TurboQuant:** The launcher is designed to work perfectly with the standard mainline `llama.cpp` build out of the box. 
- **TurboQuant KV Cache:** If you select `turbo2`, `turbo3`, or `turbo4` from the KV Cache dropdown, you **must** be using a `llama-server.exe` built from the [TurboQuant fork](https://github.com/TheTom/llama-cpp-turboquant). Selecting these options with a mainline build will result in a startup error.
- **Graceful Degradation:** If you don't install the optional Python dependencies (`psutil`, `huggingface_hub`, `pyyaml`), the launcher will still run perfectly. It will simply fall back to basic Windows commands for RAM monitoring and skip advanced HuggingFace metadata parsing.
- **Windows Optimized:** The memory monitoring, GPU detection, and background execution (`CREATE_NO_WINDOW`) are currently optimized for Windows. Linux/macOS users may need to tweak the `_fetch_memory` and `_detect_gpus` methods to use `rocm-smi` or standard Linux `/proc` parsing.

## 📖 Detailed User Guide

### 1. ⚙️ Setup Tab
* **Directories:** Point the **LLaMA Directory** to the folder containing `llama-server.exe` and the **Models Directory** to where your `.gguf` files are stored. Click **✔ Save & Apply**.
* **Config Directory:** This is where your saved presets (`llama_configs.json`) live. You can change this if you want to keep your configs in a specific folder.
* **Model Selection:** Choose your `.gguf` from the dropdown. 
* **📖 Model Info Panel:** The launcher automatically reads the model's `config.json` or HuggingFace `README.md` to display architecture, parameter count, and capabilities. 
  * *Tip:* If the auto-detection misses something, click the **✏️ Edit Card** button to manually add capabilities (like Vision, Code, MoE) or correct the parameter count.

### 2. 🎛️ Parameters & Sampling
* **Core Settings:** Set your GPU Layers (`-ngl`), KV Cache types (`-ctk`/`-ctv`), and Context Length (`-c`).
* **Speculative Decoding:** 
  * **MTP (Multi-Token Prediction):** Set "MTP Tokens" to 1-6 to use the native MTP draft.
  * **Classic/Draft:** If MTP is 0, you can use a separate Draft Model (Eagle3, N-gram, etc.). *Note: Ensure you set Draft NGL (`-ngld`) so the draft model doesn't fall back to CPU!*
* **Sampling:** Adjust Temperature, Top-K, Top-P, etc. 
  * *New:* Every sampling parameter has a **checkbox** next to it. Uncheck a box to completely remove that flag from the launch command (useful for models that require strict default sampling).

### 3. 🚀 GPU / CPU / AUTO-FIT
* **Auto-Fit (`-fit`):** Turn this **ON** to let `llama-server` automatically calculate the optimal tensor split and context size to fit perfectly into your GPU's VRAM.
* **Multi-GPU:** If you select multiple GPUs in the Setup tab, the **Tensor Split (`-ts`)** field will auto-populate based on your GPUs' VRAM. You can adjust the Split Mode (`-sm`) here.
* **NUMA / CPU:** Advanced controls for CPU pinning (`-Cr`) and NUMA distribution.

### 4. 💾 Generated Command & Configs
* **Generated Command:** Look at the top right. The launcher builds the exact PowerShell command. You can click **📋 Copy Command** to run it manually in your own terminal if you prefer.
* **Save/Load Configs:** Name your current setup in the "Save to" box and click **💾 Save**. You can load it later from the dropdown, or export/import JSON files using the **📂 Load Config File** button.

### 5. 🧪 Test Prompt & Benchmarking
* Switch to the **Test Prompt** tab.
* Type a prompt and click **▶ Send & Measure**.
* The launcher will stream the response and calculate accurate **Tokens/Second (tk/s)** and **Time-To-First-Token (TTFT)** by reading the server's internal timing data (which is much more accurate than just counting streamed chunks, especially when using MTP/Speculative decoding).

### 💡 Pro-Tips
* **Phantom Windows / Scrolling:** The UI uses a custom canvas scrolling implementation. If you have many parameters, just use your mouse wheel *while hovering over the tab* to scroll.
* **TurboQuant KV Cache:** If you see `turbo2/3/4` in the KV Cache dropdown, note that these require a custom-built TurboQuant fork of `llama-server.exe`. They will throw an error on the standard mainline build.

<img width="1385" height="1019" alt="launcher-01" src="https://github.com/user-attachments/assets/8dcc2247-1bf7-4df9-a138-f4ace7370db1" />

<img width="1383" height="1016" alt="launcher-02" src="https://github.com/user-attachments/assets/5eacd595-3430-424d-8eaa-1e5a1d50b5a1" />

