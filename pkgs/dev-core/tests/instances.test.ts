import { describe, expect, it } from "vitest";
import {
    buildSnapshot,
    displayPath,
    launchHint,
    matchLegacy,
    matchRecord,
    parseRecord,
    sameHome,
    sameApp,
    samePath,
    withPort,
    worktreeOf,
    type InstanceRecordLite,
} from "../src/instances.js";
import { homedir } from "node:os";
import type { AppSpec, WorktreeInfo } from "../src/shared.js";

const record = (patch: Partial<InstanceRecordLite> = {}): InstanceRecordLite => ({
    pid: 1234,
    app: "diy-chat",
    launch: "lab",
    worktree: "/repo",
    port: null,
    diyHome: "/repo/build/lab/1/home",
    variant: "lab",
    env: "development",
    argv: ["/electron", "build/lab/main/index.mjs"],
    cwd: "/repo/apps/chat",
    startedAt: "2026-11-02T10:00:00.000+0800",
    updatedAt: "2026-11-02T10:00:01.000+0800",
    parents: [],
    ...patch,
});

const chatApp = (dir = "/repo/apps/chat"): AppSpec => ({
    name: "chat",
    title: "diy 聊天",
    dir,
    launches: [
        {
            id: "lab",
            title: "开发（lab）",
            command: "./sha.sh lab",
            entries: [{ kind: "app", title: "Electron 窗口" }],
        },
    ],
});

const webApp = (): AppSpec => ({
    name: "web",
    title: "diy web",
    dir: "/repo/apps/web",
    launches: [
        {
            id: "web-8123",
            command: "./sha.sh lab",
            env: { PORT: "8123" },
            entries: [{ kind: "web", title: "浏览器", url: "http://localhost:8123" }],
        },
    ],
});

describe("parseRecord（宽松）", () => {
    it("缺字段给缺省值；坏 pid 整条作废", () => {
        expect(parseRecord({})).toBeNull();
        const parsed = parseRecord({ pid: 7, app: null, launch: null, worktree: null, port: "x" });
        expect(parsed?.pid).toBe(7);
        expect(parsed?.app).toBeNull();
        expect(parsed?.launch).toBeNull();
        expect(parsed?.worktree).toBeNull();
        expect(parsed?.port).toBeNull();
    });

    it("老记录（没有 launch / worktree）不报错", () => {
        const parsed = parseRecord({ pid: 7, app: "chat", diyHome: "/h", variant: "lab" });
        expect(parsed?.launch).toBeNull();
        expect(parsed?.worktree).toBeNull();
    });
});

describe("匹配键 (worktree, app, launch)", () => {
    it("app 允许 chat / diy-chat 两种历史口径", () => {
        expect(sameApp("chat", "chat")).toBe(true);
        expect(sameApp("diy-chat", "chat")).toBe(true);
        expect(sameApp("diy-chat", "minimal")).toBe(false);
        expect(sameApp(null, "chat")).toBe(false);
    });

    it("worktree 路径相等（写法不同也算同一个）", () => {
        expect(samePath("/repo", "/repo")).toBe(true);
        expect(samePath("/repo/", "/repo")).toBe(true);
        expect(samePath("/wt/t502", "/repo")).toBe(false);
        expect(samePath(null, "/repo")).toBe(false);
    });

    it("三元组全中才算同一个 launch", () => {
        const ref = { worktree: "/repo", app: "chat", launch: "lab" };
        expect(matchRecord(record(), ref)).toBe(true);
        expect(matchRecord(record({ app: "chat" }), ref)).toBe(true);
        expect(matchRecord(record({ launch: null }), ref)).toBe(false);
        expect(matchRecord(record({ app: "diy-minimal" }), ref)).toBe(false);
        expect(matchRecord(record({ worktree: "/repo/" }), ref)).toBe(true);
        expect(matchRecord(record({ worktree: "/wt/other" }), ref)).toBe(false);
    });
});

describe("数据根参与匹配（##518：真生产实例不许被当成 practice launch）", () => {
    it("三元组相同但 diyHome 不同 ⇒ 不匹配", () => {
        const ref = { worktree: "/repo", app: "chat", launch: "lab" };
        expect(matchRecord(record({ diyHome: "/repo/build/lab/1/home" }), ref, "/repo/build/lab/1/home")).toBe(true);
        // 生产实例：cwd/worktree/launch 都对，数据根是 ~/.diy ⇒ 不算这条 launch 在跑
        expect(matchRecord(record({ diyHome: "/Users/x/.diy" }), ref, "/repo/build/lab/1/home")).toBe(false);
        // 老记录写 `~/` 形态也要认
        expect(sameHome("~/build/lab/home", `${homedir()}/build/lab/home`)).toBe(true);
    });

    it("没被任何 launch 认领的记录进 externals，生产根被标 production", () => {
        const worktrees: WorktreeInfo[] = [{ path: "/repo", branch: null }];
        const snapshot = buildSnapshot(worktrees, {
            repoRoot: "/repo",
            worktrees,
            appsOf: () => [chatApp()],
            records: [
                record({ pid: 111, diyHome: "/repo/build/lab/1/home" }),
                record({ pid: 222, app: "diy-app", launch: null, worktree: null, diyHome: "/Users/x/.diy" }),
            ],
            starting: new Set(),
            builtOf: () => true,
            prodHome: "/Users/x/.diy",
        });
        expect(snapshot.launches[0]?.running).toBe(true);
        expect(snapshot.externals.map((item) => item.pid)).toEqual([222]);
        expect(snapshot.externals[0]?.production).toBe(true);
    });
});

describe("多实例（lab/1、lab/2 同属一条 launch）", () => {
    it("数据根族内的记录全部归到该 launch，instances 按启动时间排序", () => {
        const worktrees: WorktreeInfo[] = [{ path: "/repo", branch: null }];
        const app: AppSpec = {
            name: "chat",
            title: "chat",
            dir: "/repo/apps/chat",
            launches: [{ id: "lab", command: "./sha.sh lab", home: "build/lab/1/home", entries: [] }],
        };
        const snapshot = buildSnapshot(worktrees, {
            repoRoot: "/repo",
            worktrees,
            appsOf: () => [app],
            records: [
                record({ pid: 2, launch: "lab/2", diyHome: "/repo/build/lab/2/home", startedAt: "2026-11-05T02:00:00.000+0800" }),
                record({ pid: 1, launch: "lab/1", diyHome: "/repo/build/lab/1/home", startedAt: "2026-11-05T01:00:00.000+0800" }),
                // 族外（生产）不计
                record({ pid: 9, launch: "lab", diyHome: "/Users/x/.diy" }),
            ],
            starting: new Set(),
            builtOf: () => true,
        });
        const launch = snapshot.launches[0]!;
        expect(launch.running).toBe(true);
        expect(launch.instances.map((item) => item.pid)).toEqual([1, 2]);
        expect(snapshot.externals.map((item) => item.pid)).toEqual([9]);
    });
});

describe("老记录兜底（手工 ./sha.sh lab：launch = null）", () => {
    const ref = { worktree: "/repo", app: "chat", launch: "lab" };

    it("worktree 缺字段时按 cwd 归到已知 worktree（嵌套取最长）", () => {
        const rec = record({ worktree: null, cwd: "/repo/apps/chat" });
        expect(worktreeOf(rec, ["/repo", "/wt/t502"])).toBe("/repo");
        expect(worktreeOf(rec, ["/repo", "/repo/apps"])).toBe("/repo/apps");
        expect(worktreeOf(rec, ["/wt/t502"])).toBeNull();
        // 已写明的字段不重算
        expect(worktreeOf(record({ worktree: "/wt/t502" }), ["/repo"])).toBe("/wt/t502");
    });

    it("launchHint 从 argv / cwd 看得出 build/<variant>", () => {
        expect(launchHint(record())).toBe("lab");
        expect(launchHint(record({ argv: ["/electron", "/repo/build/prod/main/index.mjs"] }))).toBe("prod");
        expect(launchHint(record({ argv: ["node", "main.mjs"], cwd: "/repo/apps/web" }))).toBeNull();
    });

    it("有 build/<x> 痕迹 ⇒ 只认同名 launch；多条 launch 又没痕迹 ⇒ 不猜", () => {
        const legacy = record({ launch: null });
        expect(matchLegacy(legacy, ref, { uniqueLaunch: true })).toBe(true);
        expect(matchLegacy(legacy, ref, { uniqueLaunch: false })).toBe(true); // 痕迹 lab 命中
        expect(matchLegacy(record({ launch: null, argv: ["/electron", "build/prod/main/index.mjs"] }), ref, { uniqueLaunch: true })).toBe(
            false,
        );
        const noHint = record({ launch: null, argv: ["node", "main.mjs"] });
        expect(matchLegacy(noHint, ref, { uniqueLaunch: false })).toBe(false);
        expect(matchLegacy(noHint, ref, { uniqueLaunch: true })).toBe(true);
        // 精确记录不走兜底；别的 app 不沾
        expect(matchLegacy(record(), ref, { uniqueLaunch: true })).toBe(false);
        expect(matchLegacy(record({ launch: null, app: "diy-minimal" }), ref, { uniqueLaunch: true })).toBe(false);
    });
});

describe("home 声明的错误检测", () => {
    const worktrees: WorktreeInfo[] = [{ path: "/repo", branch: null }];
    const app = (home: string | undefined): AppSpec => ({
        name: "diy-app",
        title: "diy 管控台",
        dir: "/repo/apps/diy-app",
        launches: [
            { id: "lab", command: "./sha.sh lab", ...(home === undefined ? {} : { home }), entries: [] },
            { id: "prod", command: "./sha.sh start", ...(home === undefined ? {} : { home }), entries: [] },
        ],
    });
    const snap = (spec: AppSpec) =>
        buildSnapshot(worktrees, {
            repoRoot: "/repo",
            worktrees,
            appsOf: () => [spec],
            records: [],
            starting: new Set(),
            builtOf: () => true,
        });

    it("都声明且不同根 ⇒ 无问题", () => {
        const s = snap(app("build/lab/home"));
        // 两条同值 ⇒ duplicate（这就是 diy-app 曾经的坑）
        expect(s.launches[0]?.configIssues.map((i) => i.code)).toEqual(["home-duplicate"]);
        expect(s.launches[0]?.homeDeclared).toBe(true);
    });

    it("声明了不同根 ⇒ 干净（homeDeclared=true，configIssues 空）", () => {
        const s = snap({
            ...app("build/lab/home"),
            launches: [
                { id: "lab", command: "./sha.sh lab", home: "build/lab/home", entries: [] },
                { id: "prod", command: "./sha.sh start", home: "build/prod/home", entries: [] },
            ],
        });
        expect(s.launches.map((item) => item.configIssues)).toEqual([[], []]);
        expect(s.launches[1]?.home).toBe("/repo/build/prod/home");
    });
});

describe("withPort（配置端口 vs 实际端口）", () => {
    it("一致时原样，不一致时换端口并标 mismatch", () => {
        expect(withPort("http://localhost:8123", 8123)).toEqual({ href: "http://localhost:8123", mismatch: false });
        const actual = withPort("http://localhost:8123", 8124);
        expect(actual.href).toBe("http://localhost:8124/");
        expect(actual.mismatch).toBe(true);
    });

    it("没有实际端口（未运行）= 用配置值、不标 mismatch", () => {
        expect(withPort("http://localhost:8123", null)).toEqual({ href: "http://localhost:8123", mismatch: false });
    });
});

describe("displayPath / buildSnapshot", () => {
    it("仓库内显示相对路径，家目录缩 ~", () => {
        expect(displayPath("/repo/build/lab/1/home", "/repo")).toBe("build/lab/1/home");
        expect(displayPath(`${process.env["HOME"]}/.diy`, "/repo")).toMatch(/^~\/\.diy$/);
    });

    it("静态清单不依赖注册表：空注册表也能列出全部 launch", () => {
        const worktrees: WorktreeInfo[] = [
            { path: "/repo", branch: "main" },
            { path: "/wt/t502", branch: "t502-dev-app" },
        ];
        const appsOf = (worktree: string): AppSpec[] =>
            worktree === "/repo" ? [chatApp(), webApp()] : [chatApp("/wt/t502/apps/chat")];
        const snapshot = buildSnapshot(worktrees, {
            repoRoot: "/repo",
            worktrees,
            appsOf,
            records: [],
            starting: new Set(),
            builtOf: () => true,
            registry: "/home/u/.diy-instances",
        });
        expect(snapshot.worktreeCount).toBe(2);
        expect(snapshot.appCount).toBe(3);
        expect(snapshot.launches.map((item) => `${item.worktree}|${item.app}|${item.launch}`)).toEqual([
            "/repo|chat|lab",
            "/repo|web|web-8123",
            "/wt/t502|chat|lab",
        ]);
        expect(snapshot.runningCount).toBe(0);
        expect(snapshot.launches[1]?.entries[0]?.href).toBe("http://localhost:8123");
        // 四级树的第一层：仓库名 / 主分支（取第一个 worktree）
        expect(snapshot.repoName).toBe("repo");
        expect(snapshot.repoBranch).toBe("main");
        // 每条 launch 带上详情页要用的静态属性
        const first = snapshot.launches[0]!;
        expect(first.worktreePath).toBe("/repo");
        expect(first.env).toEqual({});
        expect(first.yamlPath).toBe("/repo/apps/chat/app.yaml");
        expect(first.home).toBe("/repo/build/lab/1/home");
    });

    it("实例 URI：nodeId 从数据根读，没有 instance-id 就是 null", () => {
        const worktrees: WorktreeInfo[] = [{ path: "/repo", branch: null }];
        const snapshot = buildSnapshot(worktrees, {
            repoRoot: "/repo",
            worktrees,
            appsOf: () => [chatApp()],
            records: [],
            starting: new Set(),
            builtOf: () => true,
            nodeIdOf: (home) => (home === "/repo/build/lab/1/home" ? "diy-9c5cdc25" : null),
        });
        expect(snapshot.launches[0]?.uri).toBe("diy://diy-9c5cdc25/chat.lab");

        const none = buildSnapshot(worktrees, {
            repoRoot: "/repo",
            worktrees,
            appsOf: () => [chatApp()],
            records: [],
            starting: new Set(),
            nodeIdOf: () => null,
        });
        expect(none.launches[0]?.uri).toBeNull();
        expect(none.launches[0]?.nodeId).toBeNull();
    });

    it("注册表按三元组对上 ⇒ running，web entry 用实际端口并标配置值", () => {
        const worktrees: WorktreeInfo[] = [{ path: "/repo", branch: "main" }];
        const snapshot = buildSnapshot(worktrees, {
            repoRoot: "/repo",
            worktrees,
            appsOf: () => [webApp()],
            records: [
                record({ pid: 4321, app: "diy-web", launch: "web-8123", worktree: "/repo", port: 8124, diyHome: "/repo/build/web-8123/1/home" }),
                record({ pid: 9999, app: "diy-chat", launch: "lab", worktree: "/repo" }),
            ],
            starting: new Set(),
            builtOf: () => true,
            memOf: () => 128 * 1024 * 1024,
            now: Date.parse("2026-11-02T10:10:00.000+0800"),
        });
        const web = snapshot.launches[0]!;
        expect(web.running).toBe(true);
        expect(web.runtime?.pid).toBe(4321);
        expect(web.runtime?.uptimeMs).toBe(10 * 60 * 1000);
        expect(web.runtime?.memBytes).toBe(128 * 1024 * 1024);
        expect(web.entries[0]?.href).toBe("http://localhost:8124/");
        expect(web.entries[0]?.configuredUrl).toBe("http://localhost:8123");
        expect(web.entries[0]?.portMismatch).toBe(true);
        // chat 的那条记录在静态清单里没有对应 launch ⇒ 不算 running（清单来自 app.yaml）
        expect(snapshot.runningCount).toBe(1);
    });

    it("app.yaml 没写 home ⇒ home-missing；多条 launch 共用一个根 ⇒ home-duplicate", () => {
        const worktrees: WorktreeInfo[] = [{ path: "/repo", branch: "main" }];
        const snapshot = buildSnapshot(worktrees, {
            repoRoot: "/repo",
            worktrees,
            appsOf: () => [chatApp(), webApp()],
            records: [],
            starting: new Set(),
            builtOf: () => true,
        });
        const chat = snapshot.launches.find((item) => item.app === "chat")!;
        // ##518：未声明 home ⇒ 按槽位推导 build/<launch>/<slot>/home，且不再报错
        expect(chat.homeDeclared).toBe(false);
        expect(chat.configIssues).toEqual([]);
        expect(chat.home).toBe("/repo/build/lab/1/home");
    });

    it("手工跑的老记录（launch / worktree 都是 null）也能对上 ⇒ running", () => {
        const worktrees: WorktreeInfo[] = [{ path: "/repo", branch: "main" }];
        const snapshot = buildSnapshot(worktrees, {
            repoRoot: "/repo",
            worktrees,
            appsOf: () => [chatApp(), webApp()],
            records: [record({ pid: 5555, app: "diy-chat", launch: null, worktree: null, cwd: "/repo/apps/chat" })],
            starting: new Set(),
            builtOf: () => true,
        });
        const chat = snapshot.launches.find((item) => item.app === "chat")!;
        expect(chat.running).toBe(true);
        expect(chat.runtime?.pid).toBe(5555);
        // web 那条 launch 不该被老记录蹭上（app 不同）
        expect(snapshot.launches.find((item) => item.app === "web")?.running).toBe(false);
        expect(snapshot.runningCount).toBe(1);
    });

    it("started 但还没注册表 ⇒ starting；未构建 ⇒ built=false", () => {
        const worktrees: WorktreeInfo[] = [{ path: "/repo", branch: null }];
        const key = `/repo\u0000chat\u0000lab`;
        const snapshot = buildSnapshot(worktrees, {
            repoRoot: "/repo",
            worktrees,
            appsOf: () => [chatApp()],
            records: [],
            starting: new Set([key]),
            builtOf: () => false,
        });
        expect(snapshot.launches[0]?.starting).toBe(true);
        expect(snapshot.launches[0]?.running).toBe(false);
        expect(snapshot.launches[0]?.built).toBe(false);
    });
});
