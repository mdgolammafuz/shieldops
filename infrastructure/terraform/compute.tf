# Node 1: Control Plane + Platform
resource "google_compute_instance" "node1" {
  name         = "shieldops-ctrl"
  machine_type = var.machine_type
  zone         = var.zone

  tags = ["shieldops", "control-plane"]

  labels = local.common_labels

  boot_disk {
    initialize_params {
      image = "ubuntu-os-cloud/ubuntu-2204-lts"
      size  = var.disk_size_gb
      type  = "pd-standard"
    }
  }

  network_interface {
    subnetwork = google_compute_subnetwork.shieldops.id
    access_config {
      # Ephemeral public IP
    }
  }

  metadata = {
    ssh-keys = "${var.ssh_user}:${file(var.ssh_public_key_path)}"
  }

  metadata_startup_script = <<-EOF
    #!/bin/bash
    set -e
    
    # Update system
    apt-get update
    apt-get install -y curl wget git vim htop net-tools
    
    # Disable swap
    swapoff -a
    sed -i '/swap/d' /etc/fstab
    
    # Set hostname
    hostnamectl set-hostname shieldops-ctrl
    
    echo "Node 1 initialization complete"
  EOF

  service_account {
    scopes = ["cloud-platform"]
  }

  allow_stopping_for_update = true
}

# Node 2: Workloads
resource "google_compute_instance" "node2" {
  name         = "shieldops-work"
  machine_type = var.machine_type
  zone         = var.zone

  tags = ["shieldops", "worker"]

  labels = local.common_labels

  boot_disk {
    initialize_params {
      image = "ubuntu-os-cloud/ubuntu-2204-lts"
      size  = var.disk_size_gb
      type  = "pd-standard"
    }
  }

  network_interface {
    subnetwork = google_compute_subnetwork.shieldops.id
    access_config {
      # Ephemeral public IP
    }
  }

  metadata = {
    ssh-keys = "${var.ssh_user}:${file(var.ssh_public_key_path)}"
  }

  metadata_startup_script = <<-EOF
    #!/bin/bash
    set -e
    
    # Update system
    apt-get update
    apt-get install -y curl wget git vim htop net-tools
    
    # Disable swap
    swapoff -a
    sed -i '/swap/d' /etc/fstab
    
    # Set hostname
    hostnamectl set-hostname shieldops-work
    
    echo "Node 2 initialization complete"
  EOF

  service_account {
    scopes = ["cloud-platform"]
  }

  allow_stopping_for_update = true
}
