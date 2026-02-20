# VPC Network
resource "google_compute_network" "shieldops" {
  name                    = "shieldops-vpc"
  auto_create_subnetworks = false
}

# Subnet
resource "google_compute_subnetwork" "shieldops" {
  name          = "shieldops-subnet"
  ip_cidr_range = "10.0.1.0/24"
  region        = var.region
  network       = google_compute_network.shieldops.id
}

# Firewall: Allow SSH
resource "google_compute_firewall" "ssh" {
  name    = "shieldops-allow-ssh"
  network = google_compute_network.shieldops.name

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["shieldops"]
}

# Firewall: Allow HTTP/HTTPS
resource "google_compute_firewall" "http" {
  name    = "shieldops-allow-http"
  network = google_compute_network.shieldops.name

  allow {
    protocol = "tcp"
    ports    = ["80", "443"]
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["shieldops"]
}

# Firewall: Allow Kubernetes API
resource "google_compute_firewall" "k8s_api" {
  name    = "shieldops-allow-k8s-api"
  network = google_compute_network.shieldops.name

  allow {
    protocol = "tcp"
    ports    = ["6443"]
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["shieldops"]
}

# Firewall: Allow NodePort range
resource "google_compute_firewall" "nodeport" {
  name    = "shieldops-allow-nodeport"
  network = google_compute_network.shieldops.name

  allow {
    protocol = "tcp"
    ports    = ["30000-32767"]
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["shieldops"]
}

# Firewall: Internal communication
resource "google_compute_firewall" "internal" {
  name    = "shieldops-allow-internal"
  network = google_compute_network.shieldops.name

  allow {
    protocol = "tcp"
    ports    = ["0-65535"]
  }

  allow {
    protocol = "udp"
    ports    = ["0-65535"]
  }

  allow {
    protocol = "icmp"
  }

  source_ranges = ["10.0.1.0/24"]
  target_tags   = ["shieldops"]
}
