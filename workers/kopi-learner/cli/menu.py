from . import commands, install, ui

_ACTIONS = [
    ("mine", "Harvest existing kopi-editor edit bundles (primary)"),
    ("documents", "Run input/ documents: Qwen + Opus (batch)"),
    ("complete", "Fill missing Opus/Qwen side for DPO pairs"),
    ("generate", "Expand from pepa-prep corpus (Opus + Qwen)"),
    ("collect", "Collect finished Opus Batch API jobs"),
    ("build", "Assemble train/val/test datasets"),
    ("train-sft", "QLoRA fine-tune toward Opus (local GPU)"),
    ("cloud-setup", "Configure Vertex target (project, bucket, GPU)"),
    ("train-cloud", "QLoRA fine-tune on Vertex AI (A100, async)"),
    ("train-status", "Check / wait on a submitted Vertex job"),
    ("pull-adapter", "Download trained adapter from GCS"),
    ("evaluate", "Held-out: base vs tuned vs Opus gold (local loop)"),
    ("evaluate-cloud", "Run held-out A/B on Vertex (CPU, async)"),
    ("eval-status", "Check / wait on a submitted eval job"),
    ("pull-eval", "Download a finished eval and score it"),
    ("eval-failures", "Bucket the last eval's guard rejections (no inference)"),
    ("train-dpo", "Preference align (after SFT + eval)"),
    ("merge", "Merge adapter for vLLM serving"),
    ("install", "Check editor link, credentials, corpus"),
]

_HANDLERS = [
    commands.mine,
    lambda: commands.documents(True),       # menu default: batch Opus (cheaper)
    lambda: commands.complete("both", None, False),
    lambda: commands.generate(None, None, None, False),
    lambda: commands.collect(None, False),
    commands.build,
    commands.train_sft,
    lambda: commands.cloud_setup(None, None, None, None, False),
    commands.train_cloud,
    lambda: commands.train_status(None, True),
    lambda: commands.pull_adapter(None),
    lambda: commands.evaluate("kopi"),
    lambda: commands.evaluate_cloud("kopi"),
    lambda: commands.eval_status(None, True),
    lambda: commands.pull_eval(None),
    commands.eval_failures,
    commands.train_dpo,
    lambda: commands.merge("sft"),
    install.run,
]


def main() -> int:
    ui.header("kopi-learner")
    while True:
        choice = ui.menu("Action", _ACTIONS)
        if choice is None:
            return 0
        ui.run_action(_HANDLERS[choice])
