import json
import sys
from pathlib import Path

# Add apps/api to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

from app.market.adapters.open_data import load_bronze_open_transfers
from app.market.merging import merge_multi_source_transfers
from app.market.ml.pipeline import ValuationMLPipeline

def main():
    print("Loading verified canonical transfer universe...")
    raw_transfers = load_bronze_open_transfers()
    merged_transfers = merge_multi_source_transfers(raw_transfers)
    print(f"Loaded and merged {len(merged_transfers)} canonical transfers.")

    pipeline = ValuationMLPipeline(random_seed=42)
    results = pipeline.run(merged_transfers, set_active=True)

    print("\n" + "="*60)
    print("PIPELINE EXECUTION SUMMARY")
    print("="*60)
    print("Release Gate Status:", results["release_gate_status"])
    print("Champion Test Metrics:")
    for k, v in results["champion_test_metrics"].items():
        print(f"  {k}: {v}")
    print("Artifact Path:", results["artifact_path"])

    out_file = Path(__file__).resolve().parents[1] / "data" / "models" / "valuation" / "pipeline_results.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"Saved results to {out_file}")

if __name__ == "__main__":
    main()
