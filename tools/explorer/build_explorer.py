"""Build the website's simulation failure explorer: stage counts, one clip per (task, policy, end stage), rollouts.js.

    build_explorer.py <stage dir> <site dir> [--encode]

End stage k = number of completed stages (round(reward_last_step * n)); k = n is success. A clip is only used if its
end stage is certain: either the seed assignment is (frame count unique among the candidate seeds, or image margin
>= MIN_MARGIN), or every seed the video could belong to (same worker slot, same number of steps) ends in the same stage.
Bin-Sort renders its bowls differently in the eval videos, so its image margins stay small; for its remaining cells the
best-margin assignment is used (bin_sort_picks.json, spot-checked by eye). Pour-Marbles starts from the same scene for every
seed, so its failure videos cannot be matched at all. Videos with decoding errors are skipped.
"""
import glob, json, os, subprocess, sys
from concurrent.futures import ThreadPoolExecutor

root, site = sys.argv[1], sys.argv[2]
MIN_MARGIN = 1.5
POLICIES = {"act": "act_{task}", "pi05": "pi05_sim", "xvla": "xvla_sim"}
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
NOTES = {"pour_marbles": "Every Pour-Marbles rollout starts from the same scene, so most of its failure videos "
                         "cannot be matched to their episodes; stages without a clip are greyed out."}

def clean(path):
    return subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-f", "null", "-"], capture_output=True,
                          text=True).stderr.strip() == ""

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
        for res in glob.glob(f"{root}/vids/evals-async*/{run}/*/{task}/results_*.json"):
            if res != sorted(glob.glob(os.path.join(os.path.dirname(res), "results_*.json")))[-1]:
                continue
            e = json.load(open(res))[0]
            for succ, prog in zip(e["success"]["values"], e["reward_last_step"]["values"]):
                k = n if succ else round(prog * n)
                assert succ or k < n, (task, policy, prog)
                counts[k] += 1
                total += 1
        clips = []
        for k in range(n + 1):
            cands = [m for m in matches if m["run"] == run and m["task"] == task and stage_certain(m)
                     and (n if m["success"] else round(m["progress"] * n)) == k]
            cands.sort(key=lambda m: (m["margin"] < MIN_MARGIN, m["seed"]))
            if not cands and task == "bin_sort" and (policy, k) in bin_sort_picks:
                cands = [bin_sort_picks[(policy, k)]]
            m = next((m for m in cands if clean(os.path.join(root, m["video"]))), None)
            if m is None:
                clips.append(None)
                continue
            out = f"static/videos/explorer/{task}_{policy}_{'success' if k == n else f'stage{k}'}.mp4"
            clips.append({"src": out, "seed": m["seed"]})
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
