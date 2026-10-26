"""Map eval head videos to episode seeds.

    RUNS='evals-async*/*' match.py <stage dir>   -> <stage dir>/matches.json

The beaker eval runs W workers x E episodes (W from merged_env_cfgs); worker w uses seeds offset + E*w + i and names
its videos "{i}_head_{timestamp}.mp4", so a video with prefix i belongs to a seed with (seed - offset) % E == i. Within each prefix group,
videos are assigned to seeds (Hungarian) by the distance between the video's first frame and the locally rendered
reset image of the seed; a pairing is only allowed if the video's frame count equals the episode's recorded steps.
`margin` = distance to the second-best allowed seed / distance to the assigned seed (inf if the frame count is unique).
"""
import glob, json, os, re, subprocess, sys
import numpy as np
from concurrent.futures import ThreadPoolExecutor
from scipy.optimize import linear_sum_assignment

root = sys.argv[1]
BIG = 1e9

def probe(v):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", v, "-frames:v", "1", "-vf", "scale=128:72:flags=bilinear",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
    n = subprocess.run(["ffprobe", "-v", "error", "-count_packets", "-select_streams", "v", "-show_entries",
                        "stream=nb_read_packets", "-of", "csv=p=0", v], capture_output=True, text=True).stdout.strip()
    if len(raw) != 128 * 72 * 3 or not n.isdigit():
        return None, -1
    return np.frombuffer(raw, np.uint8).reshape(72, 128, 3).astype(np.float32), int(n)

out = []
for res_path in sorted(glob.glob(f"{root}/vids/{os.environ.get('RUNS', '*/*')}/*/*/results_*.json")):
    run_dir = os.path.dirname(res_path)
    evals, run, step, task = run_dir.split("/")[-4:]
    if "_mixed" in run or res_path != sorted(glob.glob(f"{run_dir}/results_*.json"))[-1]:
        continue
    e = json.load(open(res_path))[0]
    start = int(e["env_cfg"]["seed"])
    seeds = list(range(start, start + len(e["steps"]["values"])))
    info = {s: dict(success=int(bool(e["success"]["values"][j])), progress=float(e["reward_last_step"]["values"][j]),
                    steps=int(e["steps"]["values"][j])) for j, s in enumerate(seeds)}
    starts = sorted(int(c["seed"]) for c in e.get("merged_env_cfgs", [e["env_cfg"]]))
    per_proc = len(seeds) // len(starts)  # episodes per worker; worker seeds are start_w + i
    R = np.load(f"{root}/resets/{task}.npz")["thumbs"].astype(np.float32)
    vids = sorted(glob.glob(f"{run_dir}/videos/*/duobench/{task}/*_head_*.mp4"))
    with ThreadPoolExecutor(16) as ex:
        probed = list(ex.map(probe, vids))
    n_ok = n_vid = 0
    for i in range(per_proc):
        group = [(v, t, n) for v, (t, n) in zip(vids, probed)
                 if t is not None and int(os.path.basename(v).split("_")[0]) == i]
        cand = [s for s in seeds if (s - start) % per_proc == i]
        if not group:
            continue
        D = np.array([[((t - R[s]) ** 2).mean() for s in cand] for _, t, _ in group])
        allowed = np.array([[n == info[s]["steps"] for s in cand] for _, _, n in group])
        C = np.where(allowed, D, BIG)
        rows, cols = linear_sum_assignment(C)
        for r, c in zip(rows, cols):
            n_vid += 1
            if not allowed[r, c]:
                continue
            v, _, frames = group[r]
            others = [D[r, k] for k in range(len(cand)) if k != c and allowed[r, k]]
            margin = (min(others) / D[r, c]) if others else float("inf")
            n_ok += 1
            out.append(dict(evals=evals, run=run, task=task, seed=cand[c], video=os.path.relpath(v, root),
                            frames=frames, dist=round(float(D[r, c]), 1), margin=round(float(margin), 3),
                            **info[cand[c]]))
    print(f"{evals:22s} {run:24s} {task:18s} videos {len(vids):3d} matched {n_ok:3d}/{n_vid:3d}", flush=True)
json.dump(out, open(f"{root}/matches{os.environ.get('TAG', '')}.json", "w"))
