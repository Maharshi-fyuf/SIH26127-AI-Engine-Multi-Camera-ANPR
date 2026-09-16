# Specialist model provenance

YUVATECH can bootstrap specialist weights from public Hugging Face repositories. The weights are not represented as YUVATECH-owned models.

| Model | Source | License | Purpose |
|---|---|---|---|
| Plate detector | `Babblu2821/alpr-plate-detector` | MIT | Indian/European plate localization |
| Helmet detector | `sharathhhhh/safetyHelmet-detection-yolov8` | Apache-2.0 | Helmet / no-helmet detection |
| Seatbelt classifier | `RISEF/yolov11s-seatbelt` | AGPL-3.0 | Driver seatbelt classification |

Run `python scripts/bootstrap_models.py --all` before production inference. Review the model licenses and domain limitations before commercial deployment. The seatbelt model is trained on a small, imbalanced windshield-view dataset; its published validation score should not be treated as YUVATECH accuracy. Re-benchmark all specialist models on YUVATECH's own representative footage before enforcement use.
