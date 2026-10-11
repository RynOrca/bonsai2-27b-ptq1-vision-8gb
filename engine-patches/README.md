# 引擎源码补丁

这是对原始NInfer源码快照2852f6f应用的补丁，不是对本部署仓库应用的补丁。可选源码包提供原始快照、补丁和本机构建参考；不要把引擎其他分支的最新源码混作该基线。

1. 在快照根目录执行`git apply --check engine-installed-fixes.patch`，再执行`git apply engine-installed-fixes.patch`。包含6个KV/lease核心文件、6处CUDA13.4/MSVC/FFmpeg适配，以及生成工具和原生回归测试。
2. `engine-optional-diagnostics.patch`只修改resource_manager.h候选拒绝日志，按需另行应用。它不属于安装470248 EXE，不需要为了正常复用而应用。

本地BuildHostInit.cmake初始化草稿未用于成功构建，且模块路径有误，因此没有收入补丁。pressure.cpp修复含已有admission诊断，不应宣称发布版完全没有诊断输出。

两个补丁已通过git apply --check。补丁不包含权重或DLL；引擎保留原Apache-2.0许可，运行库和模型各自遵守原许可。
