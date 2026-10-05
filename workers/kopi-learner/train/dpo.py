"""Run DPO preference alignment on the SFT adapter, nudging it to prefer
Opus's edit over its own, applied only after SFT is well-formed but still
occasionally picks the weaker edit.
"""
from cli import ui
from train import setup

SFT_IN = setup.ADAPTERS / "sft"
OUT = setup.ADAPTERS / "dpo"


def run() -> None:
    from peft import PeftModel
    from trl import DPOConfig, DPOTrainer

    if not (SFT_IN / "adapter_config.json").exists():
        raise SystemExit(
            "no SFT adapter at data/adapters/sft: DPO follows SFT. Run `train-sft`, then "
            "`evaluate`, and only reach for DPO if the model is well-formed but suboptimal.")
    ui.warn("DPO is the last rung (learning.md §3.4), confirm SFT plateaued on the held-out "
            "eval before spending this. Proceeding on the existing SFT adapter.")

    hp = setup._hp()
    train_ds = setup.dataset("dpo_train.jsonl")
    val_path = setup.config.data_dir() / "out" / "dpo_val.jsonl"
    eval_ds = setup.dataset("dpo_val.jsonl") if val_path.exists() else None

    ui.step(f"QLoRA DPO plan: {len(train_ds)} preference pairs -> {OUT}")
    base = setup.prepare_for_kbit_training(setup.load_base_model())
    model = PeftModel.from_pretrained(base, str(SFT_IN), is_trainable=True)

    args = DPOConfig(
        output_dir=str(OUT),
        num_train_epochs=float(hp.get("epochs", 1)),
        learning_rate=float(hp.get("learning_rate", 5e-5)),
        max_length=int(hp.get("max_seq_len", 2048)),
        per_device_train_batch_size=1,
        gradient_accumulation_steps=8,
        bf16=True,
        # Same QLoRA memory recipe as SFT (see train/sft.py); DPO also holds a
        # reference model, so checkpointing matters even more here.
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        optim="paged_adamw_8bit",
        beta=0.1,
        logging_steps=10,
        save_strategy="epoch",
        eval_strategy="epoch" if eval_ds is not None else "no",
        report_to=[],
    )
    trainer = DPOTrainer(
        model=model,
        args=args,
        train_dataset=train_ds,
        eval_dataset=eval_ds,
        processing_class=setup.load_tokenizer(),
    )
    trainer.train()
    trainer.save_model(str(OUT))
    ui.ok(f"DPO adapter saved -> {OUT}")
