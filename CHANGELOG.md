# 2026-10-12 修复清单

对比基线：GitHub main提交9d6b5dad2fdab414a77f3a16cdc30cb0d7c46134。GitHub发布这些小文件，网盘增量包待上传；默认资产清单暂留旧版。

## GitHub文件

- README.md：更新引擎身份、验证边界与接入要求，保留旧短任务记录并标明场景。
- assets-20261012.sha256：新引擎和DLL清单，模型SHA不变。默认assets.sha256暂留旧版，待网盘增量上传后再切换。
- .gitignore：允许接入示例、离线测试、源码补丁和更新说明。
- integration/：新增完整历史回传的Agent示例与说明，默认preserve_thinking=true，不设置固定思考预算。
- tests/test_interactive_agent.py：包含分片思考字段实际回传、工具循环和终态处理测试。
- engine-patches/：引擎修复/工具链适配与后续诊断分开。
- verify-assets.ps1：支持-ManifestPath选择版本清单；SHA256改用.NET流式计算，避免旧PowerShell模块路径造成Get-FileHash缺失，校验含义不变。
- start-local.bat、smoke-test.ps1：运行逻辑未改；跨请求复用、动态lease继续开启。

## 网盘文件

必须替换或新增8个文件：ninfer-serve-89.exe、avcodec-62.dll、avformat-62.dll、avutil-60.dll、swresample-6.dll、swscale-9.dll、libcurl.dll、zlib.dll。

无需重传：模型bonsai2_27b_ptq1_native_mtp_vision.ninfer、cublas64_13.dll、cublasLt64_13.dll。完整最小引擎目录包含EXE和9个第三方DLL。

旧FFmpeg63/61/10/7、cudart64_13.dll、libcurl-x64.dll不在新EXE最小依赖中，不收入新包。旧文件残留不替代新文件。不要上传backup EXE、runtime缓存或会话日志。

## 代码与验证范围

原始源码快照2852f6f：6个KV/lease核心文件、6处CUDA13.4/MSVC/FFmpeg构建适配，加2个生成工具/原生测试文件，组成发布版复现补丁。后续resource_manager.h候选诊断独立成补丁，未装入470248 EXE。

原适配器已支持reasoning_content回传。对照A人为丢弃字段，B完整回传但未传preserve选项，C完整回传且preserve=true；B/C分别0.82/0.84秒，命中51527/51551。不能把全部收益归因于新增默认true一行。模板未传/true保留历史思考，显式false会删除。

普通stop、一个ping调用和中间标记检索样本通过。A/B输入不同，不能证明缓存本身提高质量。动态工具声明可能改变较早前缀并触发冷重算；从首轮固定schema有助稳定复用，但不是所有变化都必然零命中。

开发构建整改验证PowerShell5/7，补齐320个空依赖对象，真实header更新时间可触发runtime/model重编。该脚本是本机开发工具，不是下载者启动脚本。视觉路径、多并发、Host近满和长期压力未在本轮重新验收。
