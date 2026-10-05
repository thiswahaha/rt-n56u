#!/usr/bin/env python3
"""为本次 Actions 构建覆盖 RM2100 模板中已有的功能开关。"""

import os  # 读取工作流通过 FEATURE_OVERRIDES 传入的配置字符串。
import re  # 严格校验功能名称与 y/n 值，避免修改非功能配置。
import sys  # 读取模板路径参数，并在校验失败时返回非零退出状态。
from pathlib import Path  # 读取和保存 Runner 工作区中的配置模板。


# 匹配模板中的完整功能键；机型、CPU、工具链等配置不在允许修改的范围内。
FEATURE_KEY = re.compile(r"CONFIG_FIRMWARE_(?:INCLUDE|ENABLE)_[A-Z0-9_]+")
# 匹配表单中的短名称，如 INCLUDE_OPENVPN=n；仅接受大写名称及小写 y/n。
OVERRIDE = re.compile(r"((?:INCLUDE|ENABLE)_[A-Z0-9_]+)=([yn])")


def apply_overrides(template: Path, raw: str) -> None:
    """先校验全部逗号分隔的覆盖项，再替换对应的模板行。"""
    # 空输入保持当前配置，第二次调用时也保留已应用的 Action 默认值。
    if not raw.strip():
        print("No feature overrides; keeping current RM2100 configuration.")
        return

    # 收集本次请求；任何空项、格式错误或重复键都会在写文件前报错。
    requested = {}
    # 逗号分隔多个开关；允许每一项前后有空格。
    for entry in raw.split(","):
        # fullmatch 要求整项匹配，拒绝附加命令、额外字符及 y/n 以外的值。
        match = OVERRIDE.fullmatch(entry.strip())
        if match is None:
            raise ValueError(f"Invalid feature override: {entry!r}; expected INCLUDE_NAME=y or ENABLE_NAME=n")
        # 将用户填写的短名称补全为模板中的 CONFIG_FIRMWARE_ 键。
        key = f"CONFIG_FIRMWARE_{match.group(1)}"
        # 同一次输入中的重复项直接报错，避免覆盖顺序含糊。
        if key in requested:
            raise ValueError(f"Duplicate feature override: {key}")
        # 保存该开关要求设置的 y 或 n。
        requested[key] = match.group(2)

    # 读取当前仓库的模板并保留换行符；功能是否存在由这个模板决定。
    # newline="" 禁止 Python 将 CRLF 自动转换成 LF，确保未修改的行逐字保留。
    with template.open("r", encoding="utf-8", newline="") as source:
        lines = source.read().splitlines(keepends=True)
    # 记录每个有效功能键出现的行号，以便检查缺失、重复并精确替换。
    positions = {}
    for index, line in enumerate(lines):
        # 去掉行尾换行后按第一个等号拆分；注释行不会匹配 FEATURE_KEY。
        key, separator, value = line.rstrip("\r\n").partition("=")
        # 只收集模板中已定义为 y/n 的 INCLUDE/ENABLE 功能开关。
        if separator and FEATURE_KEY.fullmatch(key) and value in {"y", "n"}:
            positions.setdefault(key, []).append(index)

    # 所有请求项都必须在模板中恰好定义一次；不允许新增其他项目的功能键。
    for key in requested:
        if len(positions.get(key, [])) != 1:
            raise ValueError(f"Feature is missing or ambiguous in {template}: {key}")

    # 仅修改请求涉及的行，其他功能、机型参数和模板注释保持原样。
    for key, setting in requested.items():
        # 获取该功能唯一的行号和原值，供修改与日志核对使用。
        index = positions[key][0]
        old = lines[index].rstrip("\r\n").partition("=")[2]
        # 保留原行的换行形式（LF 或 CRLF）。
        ending = lines[index][len(lines[index].rstrip("\r\n")):]
        # 在内存中替换配置值，再打印旧值到新值的变化。
        lines[index] = f"{key}={setting}{ending}"
        print(f"{key}: {old} -> {setting}")

    # 全部校验通过后写回 Runner 中的模板；build_firmware_modify 稍后将其复制为 trunk/.config。
    with template.open("w", encoding="utf-8", newline="") as target:
        target.write("".join(lines))


# 直接执行脚本时使用第一个命令行参数作为模板路径。
if __name__ == "__main__":
    try:
        # 环境变量未设置时按空输入处理；用户输入从不作为 Shell 命令执行。
        apply_overrides(Path(sys.argv[1]), os.environ.get("FEATURE_OVERRIDES", ""))
    # 缺少参数、读写失败或输入校验失败都向 stderr 报错，并使 Actions 步骤失败。
    except (IndexError, OSError, ValueError) as error:
        print(f"Configuration error: {error}", file=sys.stderr)
        sys.exit(1)
