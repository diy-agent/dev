// instances.ts — **动态状态**：注册表（`~/.diy-instances/*.json`）+ 进程细节 → 每条 launch 运行与否。
//
// ##502 第二轮：注册表只回答「谁活着」，不参与「有什么能启动」。
// 匹配键 = `(worktree, app, launch)`：
//   · worktree：绝对路径相等（resolve 后再比）
//   · app：注册表里的 `app` 允许写作 `<name>` 或 `diy-<name>`（历史口径并存）
//   · launch：app.yaml 里那条启动命令的 id；老记录为 null ⇒ 匹配不上（读侧不报错，只是显示未启动）
//
// 老记录（没有 launch / worktree 字段，甚至没有 app）一律宽松：parseRecord 给 null，绝不抛。

import { readdirSync, readFileSync, unlinkSync } from "node:fs";
import { homedir } from "node:os";
import { basename, join, relative, isAbsolute, resolve, sep } from "node:path";
import { registryDir as registryDirOf } from "@diy-agent/dev-paths";
import type {
    AppSpec,
    DevSnapshot,
    EntryStatus,
    LaunchConfigIssue,
    LaunchInstance,
    LaunchRuntime,
    LaunchStatus,
    WorktreeInfo,
} from "./shared.js";

/** 注册表目录：**唯一真源在 `@diy-agent/dev-paths`**（`~/.diy/dev/apps`），这里只转发 */
export function registryDir(env: NodeJS.ProcessEnv = process.env): string {
    return registryDirOf(env);
}

/** 注册表一条（宽松版：只取 UI 用得到的字段；缺字段 = 缺省值） */
export interface InstanceRecordLite {
    readonly pid: number;
    /** app 短名；老记录 = null */
    readonly app: string | null;
    /** launch id；老记录 = null */
    readonly launch: string | null;
    /** 启动它的 git worktree 根；老记录 = null */
    readonly worktree: string | null;
    readonly port: number | null;
    readonly diyHome: string;
    readonly variant: string;
    readonly env: string;
    readonly argv: readonly string[];
    readonly cwd: string;
    readonly startedAt: string;
    readonly updatedAt: string;
    readonly parents: readonly { readonly pid: number; readonly command: string }[];
}

export function parseRecord(raw: unknown): InstanceRecordLite | null {
    if (typeof raw !== "object" || raw === null) return null;
    const o = raw as Record<string, unknown>;
    if (typeof o["pid"] !== "number" || !Number.isFinite(o["pid"]) || o["pid"] <= 0) return null;
    const str = (v: unknown): string => (typeof v === "string" ? v : "");
    const nullableStr = (v: unknown): string | null => (typeof v === "string" && v !== "" ? v : null);
    const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);
    const parents = Array.isArray(o["parents"])
        ? (o["parents"] as unknown[])
              .map((h) => h as Record<string, unknown>)
              .filter((h) => typeof h["pid"] === "number" && typeof h["command"] === "string")
              .map((h) => ({ pid: h["pid"] as number, command: h["command"] as string }))
        : [];
    return {
        pid: o["pid"],
        app: nullableStr(o["app"]),
        launch: nullableStr(o["launch"]),
        worktree: nullableStr(o["worktree"]),
        port: num(o["port"]),
        diyHome: str(o["diyHome"]),
        variant: str(o["variant"]),
        env: str(o["env"]),
        argv: Array.isArray(o["argv"]) ? (o["argv"] as unknown[]).filter((x): x is string => typeof x === "string") : [],
        cwd: str(o["cwd"]),
        startedAt: str(o["startedAt"]),
        updatedAt: str(o["updatedAt"]),
        parents,
    };
}

/** pid 是否活着（EPERM = 有进程但没权限发信号 ⇒ 活着） */
export function isPidAlive(pid: number): boolean {
    if (!Number.isInteger(pid) || pid <= 0) return false;
    try {
        process.kill(pid, 0);
        return true;
    } catch (e) {
        return (e as NodeJS.ErrnoException).code === "EPERM";
    }
}

/**
 * 读全表：坏 JSON / 死进程的条目直接删掉（「关掉一个实例下次就不再出现」靠这条，
 * 退出钩子不保证执行）。目录不存在 ⇒ 空表（第一次跑，正常态）。
 */
export function readRecords(
    dir: string = registryDir(),
    alive: (pid: number) => boolean = isPidAlive,
): InstanceRecordLite[] {
    let names: string[];
    try {
        names = readdirSync(dir);
    } catch {
        return [];
    }
    const out: InstanceRecordLite[] = [];
    for (const name of names) {
        if (!name.endsWith(".json")) continue;
        const file = join(dir, name);
        let rec: InstanceRecordLite | null = null;
        try {
            rec = parseRecord(JSON.parse(readFileSync(file, "utf-8")));
        } catch {
            rec = null;
        }
        if (rec === null || !alive(rec.pid)) {
            try {
                unlinkSync(file);
            } catch {
                /* 忽略 */
            }
            continue;
        }
        out.push(rec);
    }
    return out;
}

/** 注册表里的 app 名与 app.yaml 的 name 是否指同一个 app（`chat` / `diy-chat` 两种历史口径） */
export function sameApp(recordApp: string | null, appName: string): boolean {
    if (recordApp === null) return false;
    return recordApp === appName || recordApp === `diy-${appName}`;
}

/** 路径相等（resolve 后比；不同写法 / 尾斜杠不该判成两个 worktree） */
export function samePath(a: string | null, b: string): boolean {
    if (a === null) return false;
    return resolve(a) === resolve(b);
}

/** 已知的入口变体名（`build/<variant>/...` 里的那一段） */
const KNOWN_VARIANTS = new Set(["lab", "test", "staging", "prod"]);

/**
 * 一条 launch 的**数据根族**：同一入口的所有 slot 都落在它下面。
 *
 * `build/lab/1/home` → `<worktree>/build/lab`；`build/lab/home`（老写法）→ 同样归一。
 * 多实例匹配靠它：`lab/1` 与 `lab/2` 是同一个 launch，只是数据根不同。
 */
export function homeRootOf(worktree: string, launchId: string, home?: string): string {
    // 没显式声明 ⇒ 数据根族就是 `build/<launch>`（洞位在它下面）
    if (home === undefined || home === "") return resolve(worktree, "build", launchId);
    const abs = resolve(worktree, home);
    const parts = abs.split(sep);
    if (parts[parts.length - 1] === "home") parts.pop();
    const last = parts[parts.length - 1] ?? "";
    if (last !== "" && !KNOWN_VARIANTS.has(last)) parts.pop(); // 去掉 slot 段
    return parts.join(sep) || sep;
}

/**
 * 一条 launch 的**缺省数据根**：`build/<launch>/<slot>/home`。
 *
 * 为什么由槽位推导而不是在 app.yaml 声明（##518 用户裁）：声明与实际常常对不上，
 * 而「一个入口 N 份实例」意味着数据根本来就得随槽位变 —— 声明一份固定值天生错。
 * 显式 `home:` 仍支持（旧数据 / /tmp 临时根），但那是**例外**，不是常态。
 */
export function deriveHome(worktree: string, launchId: string, slot: number | string = 1): string {
    return resolve(worktree, "build", launchId, String(slot), "home");
}

/** 数据根比较：`~/.diy` 与 `/Users/x/.diy` 视为同一个根（老记录可能带 `~`） */
export function sameHome(a: string | null, b: string | null): boolean {
    if (a === null || b === null || a === "" || b === "") return false;
    const norm = (v: string): string => {
        const expanded = v.startsWith("~/") ? join(homedir(), v.slice(2)) : v;
        return resolve(expanded);
    };
    return norm(a) === norm(b);
}

export interface LaunchRefLike {
    readonly worktree: string;
    readonly app: string;
    readonly launch: string;
}

/**
 * 这条记录是否属于这个 launch 的某个实例（##518：一个入口可以有多份 `lab/1`、`lab/2`）。
 *
 * 判据：worktree + app 相同、launch 名相同（允许 `<id>/<slot>` 后缀）、数据根落在该 launch 的
 * 数据根族里。族外一律不认 —— 真生产 `~/.diy` 因此永远不会被当成 worktree 的 launch。
 */
export function matchInstance(record: InstanceRecordLite, ref: LaunchRefLike & { readonly homeRoot: string }): boolean {
    if (!samePath(record.worktree, ref.worktree) || !sameApp(record.app, ref.app)) return false;
    const launch = record.launch ?? "";
    if (launch !== ref.launch && !launch.startsWith(`${ref.launch}/`)) return false;
    const home = resolve(record.diyHome === "" ? "." : record.diyHome);
    return home === ref.homeRoot || home.startsWith(`${ref.homeRoot}${sep}`);
}

/**
 * 这条记录是否对应这个 launch。
 *
 * 除了 `(worktree, app, launch)` 三元组，**数据根也必须一致**（##518 用户裁）：
 * 全局 `diy` 起的生产实例 `cwd` 落在主 worktree、`variant=prod`，三元组可能刚好撞上某个
 * worktree 的 prod/staging launch —— 但它跑在 `~/.diy`，不是那条 launch。少这一条就会
 * 「面板显示运行中，点停止杀掉了真生产」。
 */
export function matchRecord(record: InstanceRecordLite, ref: LaunchRefLike, expectedHome?: string): boolean {
    if (!samePath(record.worktree, ref.worktree) || !sameApp(record.app, ref.app) || record.launch !== ref.launch) return false;
    if (expectedHome === undefined) return true;
    return sameHome(record.diyHome, expectedHome);
}

/**
 * 记录的 worktree：缺字段（老记录 / 不是 workbench 装配的 app）时按 `cwd` 归属到某个已知 worktree。
 *
 * 为什么需要：`worktree` 是 ##502 才加的字段，之前的记录只有 `cwd`；没有它 `samePath(null, …)` 永远 false，
 * 明明活着的实例在启动器里也显示「未启动」。取**最长前缀**（嵌套 worktree 时归给更深的那个）。
 */
export function worktreeOf(record: InstanceRecordLite, known: readonly string[]): string | null {
    if (record.worktree !== null) return record.worktree;
    const cwd = resolve(record.cwd === "" ? "." : record.cwd);
    let best: string | null = null;
    for (const path of known) {
        const root = resolve(path);
        if (cwd !== root && !cwd.startsWith(`${root}/`)) continue;
        if (best === null || root.length > resolve(best).length) best = root;
    }
    return best;
}

/** 老记录从 argv / cwd 里能否看出 `build/<variant>/`（`lab` / `prod` 靠这个分） */
export function launchHint(record: InstanceRecordLite): string | null {
    const text = `${record.argv.join(" ")} ${record.cwd}`;
    // 前置分隔符放宽到「非路径字符」：argv 里是 `build/lab/main/index.mjs`（相对）也可能是绝对路径
    const hit = /(?:^|[^\w.-])build[/\\]([A-Za-z0-9._-]+)[/\\]/.exec(text);
    return hit?.[1] ?? null;
}

/**
 * 老记录（`launch === null`，手工 `./sha.sh lab` / 旧版自报）归给哪条 launch：
 *   · 有 `build/<x>/` 痕迹 ⇒ 只认同名 launch；
 *   · 没有痕迹 ⇒ 该 app 只有一条 launch 时才归它（多条时分不清，宁可不猜）。
 */
export function matchLegacy(record: InstanceRecordLite, ref: LaunchRefLike, options: { readonly uniqueLaunch: boolean }): boolean {
    if (record.launch !== null) return false;
    if (!samePath(record.worktree, ref.worktree) || !sameApp(record.app, ref.app)) return false;
    const hint = launchHint(record);
    return hint === null ? options.uniqueLaunch : hint === ref.launch;
}

/** 展示形式的路径：仓库内相对路径优先，其次 `~` 缩写，最后原样 */
export function displayPath(path: string, repoRoot: string): string {
    const rel = relative(resolve(repoRoot), resolve(path));
    if (rel !== "" && !rel.startsWith("..") && !isAbsolute(rel)) return rel;
    const home = homedir();
    if (path === home) return "~";
    if (path.startsWith(`${home}/`)) return `~${path.slice(home.length)}`;
    return path;
}

/** worktree 的展示名：`<家目录缩写或路径>（<分支>）` */
export function worktreeLabel(worktree: string, branch: string | null, repoRoot: string): string {
    const where = displayPath(worktree, repoRoot);
    return branch === null ? where : `${where}  ${branch}`;
}

/** 端口替换：`http://localhost:8123` + 实际端口 8124 → `http://localhost:8124` */
export function withPort(url: string, port: number | null): { href: string; mismatch: boolean } {
    if (port === null) return { href: url, mismatch: false };
    try {
        const parsed = new URL(url);
        const configuredPort =
            parsed.port !== "" ? Number(parsed.port) : parsed.protocol === "https:" ? 443 : parsed.protocol === "http:" ? 80 : null;
        if (configuredPort === port) return { href: url, mismatch: false };
        parsed.port = String(port);
        return { href: parsed.toString(), mismatch: true };
    } catch {
        return { href: url, mismatch: false };
    }
}

export interface SnapshotInputs {
    readonly repoRoot: string;
    readonly worktrees: readonly WorktreeInfo[];
    /** worktree → 所属仓库根（多仓库合并扫描时区分归属；缺省全归 repoRoot） */
    readonly repoOf?: (worktree: string) => string;
    /** worktree → apps（调用方负责 IO 与解析问题收集） */
    readonly appsOf: (worktree: string) => readonly AppSpec[];
    readonly records: readonly InstanceRecordLite[];
    /** 已拉起但还没写注册表的（key = `(worktree, app, launch)`） */
    readonly starting: ReadonlySet<string>;
    readonly problems?: readonly string[];
    /** worktree 是否构建过 */
    readonly builtOf?: (worktree: string) => boolean;
    /** pid → 内存字节数（注入：单测不跑 ps） */
    readonly memOf?: (pid: number) => number | null;
    /** 数据根 → instance-id（注入：单测不读盘）；缺省读 `<home>/instance-id` */
    readonly nodeIdOf?: (home: string) => string | null;
    readonly now?: number;
    readonly registry?: string;
    /** 真生产数据根（缺省 `~/.diy`）；用来把「生产实例」与 worktree 的沙箱区分开 */
    readonly prodHome?: string;
}

/** 数据根缺省（与 apps/* 的 sha.sh 同口径） */
export const DEFAULT_HOME = "build/lab/home";

/** 读 `<home>/instance-id`（不存在 / 空 = null；不写盘 —— 启动器只读不代建身份） */
export function readNodeId(home: string): string | null {
    try {
        const text = readFileSync(join(home, "instance-id"), "utf-8").trim();
        return text === "" ? null : text;
    } catch {
        return null;
    }
}

export function launchKey(worktree: string, app: string, launch: string): string {
    return `${resolve(worktree)}\u0000${app}\u0000${launch}`;
}

/** 纯合成：静态清单 + 注册表记录 → 每条 launch 的状态（不碰 IO，便于单测） */
export function buildSnapshot(targets: readonly WorktreeInfo[], inputs: SnapshotInputs): DevSnapshot {
    const now = inputs.now ?? Date.now();
    const memOf = inputs.memOf ?? (() => null);
    const builtOf = inputs.builtOf ?? (() => true);
    const nodeIdOf = inputs.nodeIdOf ?? readNodeId;
    const launches: LaunchStatus[] = [];
    /** 已被某条 launch 认领的记录（其余进 externals：真生产 / 孤儿实例） */
    const claimed = new Set<number>();
    let appCount = 0;
    // 老记录没有 worktree：先按 cwd 归到已知 worktree（嵌套取最长前缀），否则永远匹配不上
    const knownPaths = targets.map((item) => item.path);
    const records = inputs.records.map((rec) => {
        const worktree = worktreeOf(rec, knownPaths);
        return worktree === null || worktree === rec.worktree ? rec : { ...rec, worktree };
    });
    for (const worktree of targets) {
        const apps = inputs.appsOf(worktree.path);
        appCount += apps.length;
        const built = builtOf(worktree.path);
        for (const app of apps) {
            // 同一 app 内每个数据根被几条 launch 占着：>1 就是配置错误（同时启动会抢单实例锁）
            const homeUse = new Map<string, number>();
            for (const item of app.launches) {
                const path = resolve(worktree.path, item.home ?? DEFAULT_HOME);
                homeUse.set(path, (homeUse.get(path) ?? 0) + 1);
            }
            for (const launch of app.launches) {
                const key = launchKey(worktree.path, app.name, launch.id);
                const ref = { worktree: worktree.path, app: app.name, launch: launch.id };
                // 先按三元组精确匹配；匹配不上再给老记录（launch=null）一次机会：
                // 手工 `./sha.sh lab` / 旧版本自报的记录没有 launch，靠 build/<variant> 痕迹或「该 app 只有一条 launch」归属
                const declaredHome = launch.home !== undefined && launch.home !== "";
                const home = declaredHome ? resolve(worktree.path, launch.home as string) : deriveHome(worktree.path, launch.id);
                const homeRoot = homeRootOf(worktree.path, launch.id, launch.home);
                // 一个 launch 可有多个实例（lab/1、lab/2…）：先收齐，再按启动时间排序
                const matched = records.filter(
                    (rec) =>
                        matchInstance(rec, { ...ref, homeRoot }) ||
                        (matchLegacy(rec, ref, { uniqueLaunch: app.launches.length === 1 }) && sameHome(rec.diyHome, home)),
                );
                for (const rec of matched) claimed.add(rec.pid);
                const instances: LaunchInstance[] = matched
                    .map((rec) => ({
                        pid: rec.pid,
                        launch: rec.launch ?? launch.id,
                        diyHome: rec.diyHome,
                        startedAt: rec.startedAt,
                        port: rec.port,
                    }))
                    .sort((a, b) => a.startedAt.localeCompare(b.startedAt));
                const record = matched[0];
                const running = record !== undefined;
                const homeDeclared = declaredHome;
                // 配置问题已退役（##518）：home 由槽位推导 ⇒ 不再有「缺声明 / 同根冲突」。
                // 显式 home 只剩一个风险：同一 app 两条 launch 写死同一个根（会抢单实例锁）。
                const configIssues: LaunchConfigIssue[] = [];
                if (declaredHome && (homeUse.get(home) ?? 0) > 1) {
                    configIssues.push({
                        code: "home-duplicate",
                        message: `同一个 app 有 ${String(homeUse.get(home))} 条 launch 显式声明了同一个数据根 ${home}：同时启动会抢单实例锁`,
                        fix: "删掉 `home:` 让它按槽位推导（build/<launch>/<slot>/home），或给各自写不同的根",
                    });
                }
                const nodeId = nodeIdOf(home);
                const actualPort = running ? record.port : null;
                const entries: EntryStatus[] = launch.entries.map((entry) => {
                    if (entry.kind !== "web" || entry.url === undefined) {
                        return { ...entry, href: null, configuredUrl: entry.url ?? null, portMismatch: false };
                    }
                    const { href, mismatch } = withPort(entry.url, running ? actualPort : null);
                    return {
                        ...entry,
                        href,
                        configuredUrl: entry.url,
                        portMismatch: mismatch,
                    };
                });
                const runtime: LaunchRuntime | null =
                    record === undefined
                        ? null
                        : {
                              pid: record.pid,
                              port: record.port,
                              startedAt: record.startedAt,
                              uptimeMs: (() => {
                                  const started = Date.parse(record.startedAt);
                                  return Number.isFinite(started) ? Math.max(0, now - started) : 0;
                              })(),
                              memBytes: memOf(record.pid),
                              cmdline: record.argv.join(" "),
                              cwd: record.cwd,
                              diyHome: record.diyHome,
                          };
                const repo = inputs.repoOf?.(worktree.path) ?? inputs.repoRoot;
                launches.push({
                    key,
                    repo,
                    worktree: worktree.path,
                    worktreeLabel: worktreeLabel(worktree.path, worktree.branch, repo),
                    worktreePath: displayPath(worktree.path, repo),
                    branch: worktree.branch,
                    app: app.name,
                    appTitle: app.title,
                    launch: launch.id,
                    launchTitle: launch.title ?? launch.id,
                    command: launch.command,
                    env: launch.env ?? {},
                    appDir: app.dir,
                    yamlPath: join(app.dir, "app.yaml"),
                    home,
                    homeDeclared,
                    configIssues,
                    nodeId,
                    uri: nodeId === null ? null : `diy://${nodeId}/${app.name}.${launch.id}`,
                    built,
                    running,
                    starting: !running && inputs.starting.has(key),
                    entries,
                    instances,
                    runtime,
                });
            }
        }
    }
    // 仓库名 / 主分支：第一个 worktree（git worktree list 的首行 = 主工作树）
    const main = targets[0];
    return {
        repoRoot: inputs.repoRoot,
        repoName: main === undefined ? basename(inputs.repoRoot) : basename(main.path),
        repoBranch: main?.branch ?? null,
        registryDir: inputs.registry ?? registryDir(),
        externals: records
            .filter((rec) => !claimed.has(rec.pid))
            .map((rec) => ({
                pid: rec.pid,
                app: rec.app,
                launch: rec.launch,
                diyHome: rec.diyHome,
                worktree: rec.worktree,
                startedAt: rec.startedAt,
                port: rec.port,
                production: sameHome(rec.diyHome, inputs.prodHome ?? join(homedir(), ".diy")),
            })),
        worktreeCount: targets.length,
        appCount,
        runningCount: launches.filter((item) => item.running).length,
        problems: inputs.problems ?? [],
        launches,
    };
}
