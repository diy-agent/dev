/**
 * fullstack.ts —— **进程内全栈**夹具（##518）
 *
 * 与 `fixtures.ts` 的分工：
 *   · `fixtures.ts` = 假快照（快，验「给这份数据界面怎么画」）；
 *   · 本文件 = **真 core**：真 `discover()` / 真 `buildSnapshot()` / 真注册表 / 真临时 git 目录，
 *     只让路两处 —— 拉起真实例（`spawn`）与时间。判据见 docs/research/ui-testing-strategy.md §10。
 *
 * 为什么能在进程内跑：`dev-page` / `dev-core` / `dev-fs` 零 Electron 依赖（已核实），
 * `snapshot()` 只读盘 + 读注册表；把 DIY_HOME 指到临时目录、cwd 指到临时仓库即可。
 */
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

export interface FullStackFixture {
    readonly home: string;
    /** 临时"仓库"根（里面有 apps/<app>/app.yaml 与 .git 标记） */
    readonly repo: string;
    /** 造一条注册表记录（模拟「某个实例活着」），返回 pid */
    record(over: { app?: string; launch?: string; port?: number; worktree?: string; diyHome?: string; name?: string }): number;
    /** 删掉所有注册记录（模拟全部退出） */
    clearRecords(): void;
    /** 注册表目录（断言用） */
    readonly registryDir: string;
    cleanup(): void;
}

let seq = 20000;

/**
 * 建夹具并**设好环境**：`DIY_HOME` 与 `cwd`。
 * ⚠️ 必须在 `import("...dev-page")` **之前**调用 —— 那个模块在加载时就算 `REPO_ROOT` 与注册表目录。
 */
export function createFullStackFixture(): FullStackFixture {
    const home = mkdtempSync(join(tmpdir(), "dev-ui-fs-"));
    const repo = join(home, "repo");
    mkdirSync(join(repo, ".git"), { recursive: true });
    mkdirSync(join(repo, "apps", "chat"), { recursive: true });
    // 真实的 app.yaml 形状（见 diy 仓 apps/chat/app.yaml）：`launches:` 是列表，每项一条命令
    writeFileSync(
        join(repo, "apps", "chat", "app.yaml"),
        [
            "name: chat",
            "title: diy 聊天",
            "launches:",
            "  - id: lab",
            "    title: 开发（lab）",
            "    command: ./sha.sh lab",
            "    entries:",
            "      - kind: app",
            "        title: Electron 窗口",
            "",
        ].join("\n"),
    );

    process.env["DIY_HOME"] = home;
    process.env["DIY_INSTANCE_REGISTRY"] = join(home, "dev", "apps");
    process.chdir(repo);

    const registryDir = process.env["DIY_INSTANCE_REGISTRY"]!;
    mkdirSync(registryDir, { recursive: true });

    const write = (over: Parameters<FullStackFixture["record"]>[0]): number => {
        const pid = seq++;
        const record = {
            pid,
            app: over.app ?? "chat",
            launch: over.launch ?? "lab",
            worktree: over.worktree ?? repo,
            port: over.port ?? null,
            pingPort: null,
            diyHome: over.diyHome ?? join(repo, "build", "lab", "home"),
            variant: "lab",
            env: "development",
            argv: ["node", "fake"],
            cwd: repo,
            startedAt: new Date().toISOString(),
            updatedAt: new Date().toISOString(),
            parents: [],
            ...(over.name === undefined ? {} : { name: over.name }),
        };
        writeFileSync(join(registryDir, `${String(pid)}.json`), JSON.stringify(record, null, 2));
        return pid;
    };

    return {
        home,
        repo,
        registryDir,
        record: write,
        clearRecords: () => {
            rmSync(registryDir, { recursive: true, force: true });
            mkdirSync(registryDir, { recursive: true });
        },
        cleanup: () => {
            rmSync(home, { recursive: true, force: true });
        },
    };
}
