"""Run the supervised fine-tune that distils Opus's edits into a LoRA
adapter, training on `{messages}` rows so trl's SFTTrainer applies the same
chat template used at inference.
"""
from cli import ui
from train import setup

OUT = setup.ADAPTERS / "sft"


def run() -> None:
    from trl import SFTConfig, SFTTrainer

    hp = setup._hp()
    train_ds = setup.dataset("sft_train.jsonl")
    val_path = setup.config.data_dir() / "out" / "sft_val.jsonl"
    eval_ds = setup.dataset("sft_val.jsonl") if val_path.exists() else None

    ui.step(f"QLoRA SFT plan: {len(train_ds)} train"
            + (f" / {len(eval_ds)} val" if eval_ds else "") + f" -> {OUT}")
    ui.info(f"base {setup.base_model_id()} · 4-bit · r={hp.get('lora_r', 16)}")

    args = SFTConfig(
        output_dir=str(OUT),
        num_train_epochs=float(hp.get("epochs", 2)),
        learning_rate=float(hp.get("learning_rate", 1e-4)),
        max_length=int(hp.get("max_seq_len", 2048)),
        per_device_train_batch_size=1,
        gradient_accumulation_steps=8,
        bf16=True,
        # QLoRA memory recipe: without checkpointing, a 32B base's activations
        # alone overflow the 80GB A100 (76.8GB allocated -> OOM). use_reentrant
        # False is mandatory or grads never reach the LoRA params; paged 8-bit
        # adam keeps optimizer state small and absorbs spikes.
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        optim="paged_adamw_8bit",
        logging_steps=10,
        # save_model() below writes the servable adapter; per-epoch checkpoints
        # only add multi-GB optimizer/resume snapshots we never deploy.
        save_strategy="no",
        eval_strategy="epoch" if eval_ds is not None else "no",
        report_to=[],
    )
    trainer = SFTTrainer(
        model=setup.load_base_model(),
        args=args,
        train_dataset=train_ds,
        eval_dataset=eval_ds,
        peft_config=setup.lora_config(),
        processing_class=setup.load_tokenizer(),
    )
    trainer.train()
    trainer.save_model(str(OUT))
    ui.ok(f"SFT adapter saved -> {OUT}")
    ui.info("next: `evaluate` on the held-out test set BEFORE considering DPO (learning.md §3.4)")
