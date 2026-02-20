# ShieldOps Infrastructure
# GCP: 2 x e2-small (2GB RAM each)

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
  zone    = var.zone
}

locals {
  common_labels = {
    project     = "shieldops"
    environment = "production"
    managed_by  = "terraform"
  }
}
