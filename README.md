# Bonsai 2 27B PTQ1 Vision · Windows 8GB KVMem

供 Windows + NVIDIA Ada `sm_89` 显卡使用的非官方部署配方。模型 ID 为 `qwen3.8-27b-long`，提供 OpenAI 兼容的文本和图片接口。GitHub 仓库只保存脚本、参数和校验清单；模型与引擎请从单独的网盘文件夹下载。

> 网盘下载链接：[百度网盘](https://pan.baidu.com/s/1WRS519wzspK5TnSsPs-yaA?pwd=ipwn)，提取码：`ipwn`。

以下为旧版短任务记录，不是长输出续轮指标：
上下文：262,144
实测 decode：65.1 tok/s
prefill：500.1 tok/s
TTFT：2.3 秒
MTP 接受率：87.1%
1000-token 输出连续正确

## 2026-10-12 修复更新

修复文件已准备，网盘增量包已上传，模型不变。为避免现有下载者校验失败，默认`assets.sha256`暂时保留旧版；新引擎使用[assets-20261012.sha256](assets-20261012.sha256)，不能混用清单。以下默认下载表格仍对应旧网盘版本。

收到2026-10-12增量包并覆盖资产目录后，使用：

```powershell
.\verify-assets.ps1 -ManifestPath .\assets-20261012.sha256
```

新引擎为1,510,906,368字节，SHA256 `4702480551D4E2C84B5982BDE3B7A8FCC45F7BC59A932CB38A74A8026D15D526`。启动脚本路径和模型文件名不变。

- 修复动态KV lease约4K提前截断、长前缀Host-backed复用时的物理页准备与尾页复制问题，保留跨请求复用。
- 自建Agent须原样回传assistant的`reasoning_content`和正文，并保持模板/工具schema稳定。默认不设置固定思考预算。接入示例见[integration/AGENT_ADAPTATION.md](integration/AGENT_ADAPTATION.md)。
- 已安装发布版：首轮真实生成16384 token后，续轮输入51551、命中51527、实算24、TTFT0.82秒；续轮生成15371 token后自然停止。同一实例，未重启。另一份只增加诊断的构建验证了连续两轮满额16384，不能将两份二进制混为一份。
- 相对丢弃思考历史的对照，第二轮TTFT从66.02秒降至约0.82秒。此为样本结果，不是所有任务、全部上下文或质量保证。
- 修正开发构建依赖前缀的编码问题；正常下载运行无需安装编译工具。源码修复与可选诊断补丁见[engine-patches/README.md](engine-patches/README.md)。

详见[CHANGELOG.md](CHANGELOG.md)。本次未重新验收视觉路径、多并发、Host近满及长期压力。

## 适用范围

- 已在 Windows、RTX 4060 Laptop 8GB（`sm_89`）、32GB 系统内存上验证。RTX 40 系其他 Ada 卡可按显存情况尝试；RTX 30/50 系需要各自架构的引擎，不能使用这里的 `ninfer-serve-89.exe`。
- NVIDIA 驱动需支持随包的 CUDA 13 运行库。测试机驱动为 610.62；无须另外安装 CUDA Toolkit。
- 新运行库依赖Windows上的Visual C++2022 x64运行库；缺少MSVCP140/VCRUNTIME140时应安装微软官方x64 Redistributable。
- 显卡同时承担桌面显示，启动后通常只剩约 0.1–0.3GB 显存。请关闭动态壁纸、游戏等占显存程序。
- 视觉权重是第三方拼接的非官方制品。来源和分发提醒见 [NOTICE.md](NOTICE.md)。

## 两个文件夹怎么放

从 GitHub 下载本仓库，从网盘下载资产文件夹，解压后保持同级：

```text
任意英文路径/
├─ bonsai2-27b-ptq1-vision-8gb/          ← 本 GitHub 仓库
│  ├─ start-local.bat
│  ├─ verify-assets.ps1
│  ├─ smoke-test.ps1
│  └─ assets.sha256
└─ bonsai2-27b-ptq1-vision-8gb-assets/   ← 网盘文件夹，不进 Git
   ├─ models/
   │  └─ bonsai2_27b_ptq1_native_mtp_vision.ninfer
   └─ engine/
      ├─ ninfer-serve-89.exe
      └─ 9 个运行 DLL
```

两条路径都尽量使用英文/ASCII 字符。模型和引擎不要改名。完整性清单：[assets.sha256](assets.sha256)。核心文件大小及 SHA256：


| 文件                    | 字节            | SHA256                                                             |
| --------------------- | ------------- | ------------------------------------------------------------------ |
| 视觉 PTQ1 `.ninfer`     | 6,690,515,712 | `40B63AB055FD41069BB2E885A38596BA326754E94829BBA7669CFDA2F81E56F4` |
| `ninfer-serve-89.exe` | 1,511,845,888 | `19222A2A68DF6F7D87889EE3B33BEDF2F3486EA309B6394A8F8A1A412262771E` |


GitHub [普通 Git 文件上限为 100 MiB](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github)，因此这两件文件以及 DLL 都不在仓库里。

## 安装与启动

在仓库目录打开 PowerShell：

```powershell
.\verify-assets.ps1
.\start-local.bat
```

若执行策略阻止 `.ps1`，仅在当前命令中使用：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\verify-assets.ps1
```

先确认校验脚本最后输出 `failed=0`。首次启动可能需要校准设备路由，之后结果缓存在本地 `.local/runtime`。不启动模型、只检查资产路径时运行 `start-local.bat --check`。如果把网盘文件夹放在别处，可先设置环境变量 `ASSET_DIR` 指向该文件夹，再运行校验脚本的 `-AssetsDir` 参数和启动脚本。

出现 `engine ready` 和 `listening on http://127.0.0.1:18200` 后，可用：

```powershell
.\smoke-test.ps1
.\smoke-test.ps1 -ImagePath C:\path\to\your.png
```

也可用 `curl.exe http://127.0.0.1:18200/v1/models` 查看模型。API Base URL 是 `http://127.0.0.1:18200/v1`，模型 ID 是 `qwen3.8-27b-long`。在运行窗口按 `Ctrl+C` 停止。

如果本机 18200 已由其他服务占用，请先停止那个服务。本脚本默认只监听回环地址；从另一台电脑访问时，应通过你自己配置的可信代理或 Tailscale Serve 转发 18200，不要直接把无鉴权接口暴露到公网。

## 参数与取舍


| 项目       | 本配置                    | 用意                       |
| -------- | ---------------------- | ------------------------ |
| 逻辑上下文    | 262,144 token          | 服务端声明的上限，不等于该长度已通过完整质量验收 |
| GPU KV 池 | 16,000 token，`rk4v4`   | 8GB 显存中保留非零工作集           |
| Host KV  | 8,192 MiB              | 超出 GPU 池的 KV 放到系统内存      |
| 并发       | 1                      | KVMem 和 8GB 显存下避免资源争用    |
| 推测解码     | MTP，draft 4            | 提高可预测输出的速度               |
| 图像       | `overlay`，merged 8,192 | 视觉塔留在内存，编码图片时临时借显存       |
| 预填块      | 128                    | 降低启动运行时显存                |


`start-local.bat` 还启用了 `--no-cuda-graph`、`--device-state-slots 0`、`--ngram-draft-tokens 0`、`--max-shared-prefixes 0`、`--kv-lease-growth` 和 `--recover-invariant-failures`。KVMem 的 ring、host-backed reuse、content scoring 保持开启。不要设置 `NINFER_TERNARY_KVMEM=0`。

实测的短任务文本解码约 64–65 token/s，任务类型、MTP 接受率和显卡频率会改变速度。图像请求已正确读出测试图的标题、3 个红圈和蓝色方块。

## 已知限制

- 本次修复通过了已复现的文本长输出截断和Host-restore用例；旧版约56K、4张图片、8K输出预算的混合场景尚未复测，不能认定所有B01边界消失。出错时保存工作并检查`/health`，不要无限自动重试。
- 高强度思考在部分提示上可能反复输出同一段推理；日常 Agent 用 `medium` 或关闭思考更稳。
- `overlay` 在 8GB 卡上的显存余量很小。启动失败时先释放显存；不能通过减小设备池就断言长上下文质量不变。
- 图片请求中把 `image_url` 放在文本之前，`detail` 用 `auto`。图片被静默忽略时应检查提示 token 数和输出是否真的引用图片细节。

本仓脚本和文档以 Apache-2.0 发布；这**不**给模型、引擎或 CUDA/FFmpeg DLL 重新授权。第三方文件应遵守各自来源的许可和分发条件。项目与 Prism ML、NInfer 作者无官方关联。

---

**English quick start:** Download this repository and the separate assets folder, keep them as siblings, run `verify-assets.ps1`, then run `start-local.bat`. Tested on Windows with an 8GB RTX 4060 Laptop (`sm_89`) and 32GB RAM. API: `http://127.0.0.1:18200/v1`, model: `qwen3.8-27b-long`. The model and engine binaries are not included in GitHub.
