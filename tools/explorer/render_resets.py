"""Render the head-camera image after reset(seed) for a DuoBench task, like vlagents' RCSDuoBench env.

    render_resets.py <task> <first_seed> <n_seeds> <out.npz> [--png DIR]
"""
import sys, os
import numpy as np
import gymnasium as gym
from PIL import Image

task, first, n, out = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
png_dir = sys.argv[sys.argv.index("--png") + 1] if "--png" in sys.argv else None

import rcs  # noqa: F401
import importlib
importlib.import_module(f"duobench.tasks.{task}")
from rcs._core.sim import SimConfig
from rcs.envs.base import ControlMode, RelativeTo

env_id = f"duobench/{task}"
cfg = gym.spec(env_id).entry_point.config()
cfg.wrapper_cfg.binary_gripper = True
cfg.headless = True
cfg.sim_cfg = SimConfig(async_control=True, realtime=False, frequency=30, max_convergence_steps=500)
cfg.control_mode = ControlMode.JOINTS
cfg.relative_to = RelativeTo.NONE
env = gym.make(env_id, cfg=cfg)

thumbs = []
for seed in range(first, first + n):
    obs, info = env.reset(seed=seed)
    img = obs["frames"]["head"]["rgb"]["data"]
    if png_dir:
        Image.fromarray(img).save(os.path.join(png_dir, f"{task}_{seed}.png"))
    thumbs.append(np.asarray(Image.fromarray(img).resize((128, 72), Image.Resampling.BILINEAR)))
np.savez_compressed(out, seeds=np.arange(first, first + n), thumbs=np.stack(thumbs))
print("done", task, first, n, thumbs[0].shape)
