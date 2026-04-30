# sdn-nids-ml

The sdn-nids-ml project is a software-defined networking (SDN) experiment that integrates network intrusion detection and machine learning. It uses Mininet to simulate a network topology, Ryu as the SDN controller, and Docker containers for web and database servers. Traffic flows are captured and processed into features for training machine learning models.

## Topology

![Topology](assets/topology.drawio.svg)

## How it works

Traffic is generated between hosts in the Mininet topology. The Ryu controller manages routing and flow rules. A packet capture script extracts flow features into CSV files. An autoencoder model is trained on normal traffic to learn typical patterns. During inference, new flows are analyzed in real-time, and those with high reconstruction error are flagged as anomalies (potential attacks).

## Machine Learning model
The autoencoder is a neural network that learns to compress and reconstruct input data. By training it on normal traffic, it learns the underlying structure of benign flows. When it encounters anomalous traffic (e.g., attack patterns), it struggles to reconstruct it accurately, resulting in a high reconstruction error. This error is used as an anomaly score to identify potential intrusions.

## Project Layout

```
sdn-nids-ml/
├── create_topology.py      # Mininet topology definition
├── l3_controller.py        # Ryu SDN controller (L3 routing)
├── capture_flows.py        # Packet capture → CSV feature extractor
├── build_docker_images.sh  # Builds web_srv and db_srv Docker images
├── run_experiment.sh       # Orchestrates routing, capture, and traffic
├── setup_routing.sh        # Configures static routes on hosts
├── assets/
│   └── topology.drawio     # Network topology diagram
├── captures/               # Output CSVs from flow capture
├── db_srv/                 # MySQL Docker service
│   ├── Dockerfile
│   ├── init.sql
│   └── start.sh
├── hosts/
│   └── traffic_gen.py      # Per-host traffic generator
├── ml/
│   ├── autoencoder.py      # Model training script
│   ├── autoencoder.ipynb   # Training notebook
│   ├── inference.py        # Real-time anomaly detection
│   ├── environment.yml     # Conda environment spec
│   └── autoencoder_model.h5 / anomaly_threshold.txt  # Trained artifacts
└── web_srv/                # Nginx + Python web service
    ├── Dockerfile
    ├── nginx.conf
    └── web_server.py
```

## Installation

**1. System dependencies** (controller + topology):

```bash
sudo pip3 install scapy
```

**2. ML environment** (conda):

```bash
conda env create -f ml/environment.yml
```

**3. Docker images**:

```bash
sudo bash build_docker_images.sh
```

## Running the Experiment

Two separate terminals are needed.

**Terminal 1** — Start the Ryu controller:

```bash
ryu-manager ryu.app.rest_router ryu.app.ofctl_rest l3_controller.py
```

**Terminal 2** — Start the topology (wait for the controller to be ready):

```bash
sudo python3 create_topology.py
```

**Terminal 3** — Configure routing, start flow capture, and start traffic generators:

```bash
# All hosts generate normal traffic; all flows labelled 'normal'
sudo bash run_experiment.sh [--timeout]

# h11 generates periodic HTTP floods (40 s every 2 min);
# h11 flows labelled 'attack', all others 'normal'
sudo bash run_experiment.sh --attack [--timeout]
```

**Terminal 4** — Train the model and run inference:

```bash
# Activate the ML environment
conda activate ml

# Train the autoencoder model
python ml/autoencoder.py

# Run real-time inference (leave running while experiment is active) 
python ml/inference.py # !! check if the right csv file is being read !!
```