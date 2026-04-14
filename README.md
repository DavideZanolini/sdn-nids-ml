# sdn-nids-ml

## Setup

Install dependencies:

```bash
sudo pip3 install scapy
```

Build the Docker images:

```bash
sudo bash build_docker_images.sh
```

## Running the Experiment

Three separate terminals are needed.

**Terminal 1** — Start the Ryu controller:

```bash
ryu-manager ryu.app.rest_router ryu.app.ofctl_rest l3_controller.py
```

**Terminal 2** — Start the topology (wait for the controller to be ready):

```bash
sudo python3 create_topology.py
```

**Terminal 3** — Configure routing and start traffic:

```bash
sudo bash run_experiment.sh
```

## Capturing Flows for Training

In a **4th terminal**, run the flow capture while the experiment is running:

```bash
sudo python3 captures/capture_flows.py --iface core-eth1 --timeout 300
```

This sniffs packets on `core-eth1`, aggregates them into flows, and saves features to a CSV in `captures/`.