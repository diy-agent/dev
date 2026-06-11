"""ShellTest API 意图测试。

每个测试 = ShellTest 的一条可执行需求文档。
形式参考 test_dai_task_intent.py——干净的 setup，直接验证契约，
使用 assert_session 做多行 transcript 式断言。
"""

from _shelltest import ShellTest


def test_intent_exit_code_direct():
    """退出码从 PS1 内嵌的 $? 自动捕获，不需要命令里 echo $?。

    也不拦截非零退出码——像真 bash 一样，$? 自取。
    """
    sh = ShellTest()
    sh.assert_session("$ true")
    sh.assert_session("$ false; echo $?\n1")


def test_intent_separate_channels():
    """stdout 和 stderr 各自独立返回，不混淆。"""
    ShellTest().assert_session("""
        $ echo out; echo err >&2
        out
        ---
        err
    """)


def test_intent_stateful_session():
    """环境变量跨 run() 持久。

    用显式 session() 而非 assert_session() 来展示状态保持。
    ShellTest 不开进程，.session() 才开。
    """
    with ShellTest().session() as s:
        s.run("export MSG=world")
        code, out, _ = s.run("echo $MSG")
        assert code == 0
        assert out == "world"


def test_intent_error_output_separate():
    """命令失败时 stderr 有内容，stdout 空，后续命令不受影响。

    assert_session 内部自动开/关 session。
    """
    ShellTest().assert_session("""
        $ cat /nonexistent_file_xyz
        ---
        {{regex:.*No such file.*}}

        $ echo still ok
        still ok
    """)


def test_intent_sentinel():
    """{{*}} 匹配任意内容，{{regex:...}} 匹配正则。"""
    ShellTest().assert_session("""
        $ echo '任务 #42 创建成功'
        任务 * 创建成功

        $ echo '2026-06-10 12:00:00  INFO 启动完成'
        {{regex:\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}}} * INFO *
    """)


def test_intent_ps1_readonly():
    """PS1 被 readonly 保护，用户写入报错，marker 不受影响。

    实现: Session.__init__ 在设置 PS1 后调用 readonly PS1。
    bash 尝试改 readonly variable 会报错到 stderr 并返回 1，
    但 prompt marker 保留，后续命令正常解析。
    """
    with ShellTest().session() as s:
        code, _, err = s.run("PS1=HAHA")
        assert code == 1
        assert "readonly" in err

        code, out, _ = s.run("echo still works")
        assert code == 0
        assert out == "still works"


def test_intent_ps1_prefix_readable():
    """ps1_prefix 让 prompt 可读，marker 仍在行中可解析。

    \\w 展开为 cwd，\\$ 展开为 $。
    默认 prefix="" 时 marker 在行首（旧行为）。
    """
    with ShellTest(ps1_prefix=r"\w\$ ").session() as s:
        # 正常命令 — marker 可解析
        code, out, _ = s.run("echo hello")
        assert code == 0
        assert out == "hello"

        # stderr 最后一行包含 prefix + marker
        _, _, err = s.run("true")
        last_line_lines = [l for l in err.strip().split("\n") if l.strip()]
        if last_line_lines:
            # prefix 展开后含路径（如 /var/...），marker 在同一行
            assert "__ST_" in last_line_lines[-1]
