# sdn-nids-ml

The sdn-nids-ml project is a software-defined networking (SDN) experiment that integrates network intrusion detection and machine learning. It uses Mininet to simulate a network topology, Ryu as the SDN controller, and Docker containers for web and database servers. Traffic flows are captured and processed into features for training machine learning models.

## Network Topology

The network topology used in this experiment is shown below:

![Topology](assets/topology.drawio.svg)

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
sudo python3 capture_flows.py --iface core-eth1 --timeout 300
```

This sniffs packets on `core-eth1`, aggregates them into flows, and saves features to a CSV in `captures/`.