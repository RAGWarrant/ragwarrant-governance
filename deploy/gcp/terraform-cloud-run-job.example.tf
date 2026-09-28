# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

variable "project_id" {
  type    = string
  default = "<gcp-project-id>"
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "image" {
  type    = string
  default = "RAGWARRANT_IMAGE_REFERENCE_PLACEHOLDER"
}

resource "google_cloud_run_v2_job" "ragwarrant" {
  name     = "ragwarrant-governance-job"
  location = var.region
  project  = var.project_id

  template {
    template {
      containers {
        image = var.image
        args = [
          "run-governance-job",
          "--config",
          "/inputs/public_mini_governance_job.yaml",
          "--output-root",
          "/outputs",
          "--decision-out",
          "/outputs/promotion_decision.json",
        ]
        env {
          name  = "RAGWARRANT_STORAGE_MODE"
          value = "local"
        }
        env {
          name  = "RAGWARRANT_INPUT_DIR"
          value = "/inputs"
        }
        env {
          name  = "RAGWARRANT_OUTPUT_DIR"
          value = "/outputs"
        }
      }
      max_retries = 0
    }
  }
}
