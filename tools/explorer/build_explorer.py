"""Build the website's simulation failure explorer: stage counts, one clip per (task, policy, end stage), rollouts.js.

    build_explorer.py <stage dir> <site dir> [--encode]

End stage k = number of completed stages (round(reward_last_step * n)); k = n is success. A clip is only used if its
end stage is certain: either the seed assignment is (frame count unique among the candidate seeds, or image margin
>= MIN_MARGIN), or every seed the video could belong to (same worker slot, same number of steps) ends in the same stage.
Bin-Sort renders its bowls differently in the eval videos, so its image margins stay small; for its remaining cells the
best-margin assignment is used (bin_sort_picks.json, spot-checked by eye). Pour-Marbles starts from the same scene for every
seed, so its failure videos cannot be matched at all. Videos with decoding errors are skipped. Stages the matching
cannot cover take a clip from a video-only re-run with seed-tagged names (VIDEO_RERUNS).

Tasks in TAGGED were re-evaluated later (Join-Blocks with the stricter success check, Block-Balance with sequential
stages). Those evals name their videos <i>_seed<N>_<success|fail>[_stage<k>]_<camera>_<time>.mp4, so their counts and clips come straight from that eval, without matching.
"""
import csv, glob, json, os, subprocess, sys
from concurrent.futures import ThreadPoolExecutor

root, site = sys.argv[1], sys.argv[2]
MIN_MARGIN = 1.5
POLICIES = {"act": "act_{task}", "pi05": "pi05_sim", "xvla": "xvla_sim"}
TAGGED = {"join_blocks": "evals-jbcheck-async*", "block_balance": "evals-bbcheck-async*"}
# Video-only re-runs with seed-tagged names (same checkpoints and seeds). They fill stages the matching could not cover;
# counts still come from the original eval, and the clip is a rollout that ended at that stage in the re-run.
VIDEO_RERUNS = {t: "evals-jbcheck-async*" for t in ("pour_marbles", "transfer_cube", "transfer_reorient", "bin_sort")}
WEKA = "/weka/robots-default/tobiasj/duobench_rerun"
# Per-seed end stages for TAGGED tasks whose evals lack a results JSON for some shards; counts come from here instead,
# and clips from the video index (policy_run, seed, success, stage, camera, path), preferring a local copy.
STAGE_CSV = {"block_balance": f"{WEKA}/bbcheck_block_balance_per_seed.csv"}
VIDEO_INDEX = {"block_balance": (f"{WEKA}/bbcheck_block_balance_videos.csv",
                                 "/home/tobiasj/scratch-duobench/bbcheck_videos")}
tasks = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "tasks.json")))
matches = json.load(open(f"{root}/matches_all.json"))

def run_of(policy, task):
    return POLICIES[policy].format(task=task)

# per eval dir/run/task: seed -> (end stage, steps) and the worker slot of each seed
blocks = {}
for res in glob.glob(f"{root}/vids/evals-async*/*/*/*/results_*.json"):
    if res != sorted(glob.glob(os.path.join(os.path.dirname(res), "results_*.json")))[-1]:
        continue
    evals, run, _, task = os.path.dirname(res).split("/")[-4:]
    if task not in tasks:
        continue
    e = json.load(open(res))[0]
    n = len(tasks[task]["stages"])
    start = int(e["env_cfg"]["seed"])
    per_proc = len(e["steps"]["values"]) // len(e.get("merged_env_cfgs", [e["env_cfg"]]))
    blocks[(evals, run, task)] = {
        start + j: (n if succ else round(prog * n), int(st), j % per_proc)
        for j, (succ, prog, st) in enumerate(zip(e["success"]["values"], e["reward_last_step"]["values"], e["steps"]["values"]))
    }

def stage_certain(m):
    if m["margin"] >= MIN_MARGIN:
        return True
    block = blocks[(m["evals"], m["run"], m["task"])]
    _, steps, slot = block[m["seed"]]
    return len({k for k, st, sl in block.values() if st == steps and sl == slot}) == 1

bin_sort_picks = {(x["policy"], x["k"]): x for name, x in json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "bin_sort_picks.json"))).items()
                  if name.endswith("_0")}
NOTES = {}

def clean(path):
    return subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-f", "null", "-"], capture_output=True,
                          text=True).stderr.strip() == ""

def stage_seeds(pattern, n):
    """end stage -> [(seed, results dir)] from the newest results JSON of every dir matching pattern"""
    out = {}
    for d in glob.glob(pattern):
        res = sorted(glob.glob(f"{d}/results_*.json"))[-1]
        e = json.load(open(res))[0]
        for j, (succ, prog) in enumerate(zip(e["success"]["values"], e["reward_last_step"]["values"])):
            out.setdefault(n if succ else round(prog * n), []).append((int(e["env_cfg"]["seed"]) + j, d))
    return out

def tagged_clip(task, n, k, by_stage):
    """first clean head video of a rollout that ended at stage k, from an eval with seed-tagged video names;
    looks next to the local results JSON first, then in the same place on weka"""
    outcome = "success" if k == n else "fail"
    for seed, d in sorted(by_stage.get(k, [])):
        rel = os.path.relpath(d, f"{root}/vids")
        for base in (d, f"{WEKA}/{rel}"):
            for v in glob.glob(f"{base}/videos/*/duobench/{task}/*_seed{seed}_{outcome}_*head_*.mp4"):
                if clean(v):
                    return {"seed": seed, "video": v}
    return None

data, jobs = {}, []
for task, meta in tasks.items():
    n = len(meta["stages"])
    data[task] = {"name": meta["name"], "stages": meta["stages"]}
    if task in NOTES:
        data[task]["note"] = NOTES[task]
    for policy in POLICIES:
        run = run_of(policy, task)
        counts = [0] * (n + 1)
        total = 0
        tagged = {}  # end stage -> [(seed, eval dir)] for TAGGED tasks
        indexed = {}  # end stage -> [(seed, video)] for STAGE_CSV tasks
        if task in STAGE_CSV:
            for row in csv.DictReader(open(STAGE_CSV[task])):
                if row["policy_run"] == run:
                    counts[n if int(row["new_success"]) else int(row["new_stage"])] += 1
                    total += 1
            index, local = VIDEO_INDEX[task]
            for row in csv.DictReader(open(index)):
                if row["policy_run"] == run and row["camera"] == "head":
                    v = os.path.join(local, run, os.path.basename(row["path"]))
                    k = n if int(row["success"]) else int(row["stage"])
                    indexed.setdefault(k, []).append((int(row["seed"]), v if os.path.exists(v) else row["path"]))
        for res in [] if task in STAGE_CSV else glob.glob(
                f"{root}/vids/{TAGGED.get(task, 'evals-async*')}/{run}/*/{task}/results_*.json"):
            if res != sorted(glob.glob(os.path.join(os.path.dirname(res), "results_*.json")))[-1]:
                continue
            e = json.load(open(res))[0]
            for j, (succ, prog) in enumerate(zip(e["success"]["values"], e["reward_last_step"]["values"])):
                k = n if succ else round(prog * n)
                assert succ or k < n, (task, policy, prog)
                counts[k] += 1
                total += 1
                tagged.setdefault(k, []).append((int(e["env_cfg"]["seed"]) + j, os.path.dirname(res)))
        rerun = tagged if task in TAGGED else (stage_seeds(f"{root}/vids/{VIDEO_RERUNS[task]}/{run}/*/{task}", n)
                                               if task in VIDEO_RERUNS else {})
        clips = []
        for k in range(n + 1):
            m = None
            if task not in TAGGED:
                cands = [m for m in matches if m["run"] == run and m["task"] == task and stage_certain(m)
                         and (n if m["success"] else round(m["progress"] * n)) == k]
                cands.sort(key=lambda m: (m["margin"] < MIN_MARGIN, m["seed"]))
                if not cands and task == "bin_sort" and (policy, k) in bin_sort_picks:
                    cands = [bin_sort_picks[(policy, k)]]
                m = next((m for m in cands if clean(os.path.join(root, m["video"]))), None)
            if m is None and counts[k] and task in STAGE_CSV:
                m = next(({"seed": seed, "video": v} for seed, v in sorted(indexed.get(k, []))
                          if os.path.exists(v) and clean(v)), None)
            elif m is None and counts[k]:
                m = tagged_clip(task, n, k, rerun)
                if m and task not in TAGGED:
                    m["rerun"] = True
            if m is None:
                clips.append(None)
                continue
            out = f"static/videos/explorer/{task}_{policy}_{'success' if k == n else f'stage{k}'}.mp4"
            clips.append({"src": out, "seed": m["seed"], **({"rerun": True} if m.get("rerun") else {})})
            jobs.append((os.path.join(root, m["video"]), os.path.join(site, out)))
        data[task][policy] = {"total": total, "counts": counts, "clips": clips}
        print(f"{task:18s} {policy:5s} n={total} counts={counts} clips={[c is not None for c in clips]}")

def encode(job):
    src, dst = job
    if os.path.exists(dst):
        return
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-an", "-vf", "scale=768:432", "-c:v", "libx264",
                    "-preset", "slow", "-crf", "31", "-pix_fmt", "yuv420p", "-movflags", "+faststart", dst], check=True)

if "--encode" in sys.argv:
    with ThreadPoolExecutor(8) as ex:
        list(ex.map(encode, jobs))
with open(os.path.join(site, "static/js/rollouts.js"), "w") as f:
    f.write("// Generated by build_explorer.py from the 300-rollout simulation evaluation (seeds 0-299).\n")
    f.write("// counts[k] = rollouts that complete k stages (last index = success); clips[k] = one such rollout.\n")
    f.write("window.DUOBENCH_ROLLOUTS = " + json.dumps(data, separators=(",", ":")) + ";\n")
print(len(jobs), "clips")
