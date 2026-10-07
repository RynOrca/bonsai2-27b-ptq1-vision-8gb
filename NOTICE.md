# 来源与分发说明

本仓库是社区部署脚本与说明，不是 Prism ML、Qwen 或 NInfer 的官方发布。

- 基础模型为 [Prism ML 的 Ternary Bonsai 2 27B](https://huggingface.co/prism-ml/Ternary-Bonsai-2-27B-gguf)。此处使用的 `.ninfer` 是第三方把 PTQ1 文本/MTP 载荷和视觉塔按 binding 拼接的非官方制品；原分享包标注“仅作技术交流，请勿用于商业用途”。
- 引擎基于 NInfer/KVMem 工作。参考公开的[源码与说明](https://modelscope.cn/models/shensanshu/ninfer-master-shensanshu-kvmem)，其仓库注明 Apache-2.0 适用于源码而不覆盖模型权重。
- 引擎目录附带 NVIDIA CUDA、FFmpeg 与 libcurl 运行库；这些文件在网盘资产目录，分别受其原许可约束。请保留原始作者包中的许可与声明。公开上传网盘前，发布者应确认自己有权再分发模型及二进制运行库。
- 本 GitHub 仓库不包含模型、引擎、运行 DLL、私有日志、会话数据或个人配置。本仓 `LICENSE` 仅覆盖本仓新写的脚本与文档。

为核对下载文件，请使用仓库中的 `assets.sha256` 与 `verify-assets.ps1`。哈希只证明文件与此配置的测试制品一致，不代表官方认证。
