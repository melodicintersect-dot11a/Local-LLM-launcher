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

## 📋 Prerequisites

1. **Python 3.10+** installed on your system.
2. **`llama-server.exe`**: Download the latest release from the [llama.cpp releases page](https://github.com/ggerganov/llama.cpp/releases).
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
