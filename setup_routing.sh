#!/bin/bash
API_URL="http://localhost:8080/router"

echo "Waiting for Ryu rest_router to be available..."
sleep 2

# DPIDs:
# sa = 000000000000000a
# core = 000000000000000c
# sb = 000000000000000b
# sb1 = 00000000000000b1
# sb2 = 00000000000000b2
# sb3 = 00000000000000b3

echo "1. Configuring Default Gateways for Hosts on Edge Switches"
# Configure switch 'sa' to act as the gateway for the 192.168.0.x subnet
curl -X POST -d '{"address": "192.168.0.254/24"}' $API_URL/000000000000000a

# Configure switch 'sb1' to act as the gateway for the 10.0.1.x subnet
curl -X POST -d '{"address": "10.0.1.254/24"}' $API_URL/00000000000000b1

# Configure switch 'sb2' to act as the gateway for the 10.0.2.x subnet
curl -X POST -d '{"address": "10.0.2.254/24"}' $API_URL/00000000000000b2

# Configure switch 'sb3' to act as the gateway for the 10.0.3.x subnet
curl -X POST -d '{"address": "10.0.3.254/24"}' $API_URL/00000000000000b3

echo -e "\n\n2. Configuring Core Switch Public IP"
# Configure switch 'core' with its public IP
curl -X POST -d '{"address": "8.8.8.8/24"}' $API_URL/000000000000000c

echo -e "\n\n3. Configuring Transit Networks between switches"

# sa to core link (10.10.1.x)
curl -X POST -d '{"address": "10.10.1.1/24"}' $API_URL/000000000000000a
curl -X POST -d '{"address": "10.10.1.2/24"}' $API_URL/000000000000000c

# core to sb link (10.10.2.x)
curl -X POST -d '{"address": "10.10.2.1/24"}' $API_URL/000000000000000c
curl -X POST -d '{"address": "10.10.2.2/24"}' $API_URL/000000000000000b

# sb to sb1 link (10.10.3.x)
curl -X POST -d '{"address": "10.10.3.1/24"}' $API_URL/000000000000000b
curl -X POST -d '{"address": "10.10.3.2/24"}' $API_URL/00000000000000b1

# sb to sb2 link (10.10.4.x)
curl -X POST -d '{"address": "10.10.4.1/24"}' $API_URL/000000000000000b
curl -X POST -d '{"address": "10.10.4.2/24"}' $API_URL/00000000000000b2

# sb to sb3 link (10.10.5.x)
curl -X POST -d '{"address": "10.10.5.1/24"}' $API_URL/000000000000000b
curl -X POST -d '{"address": "10.10.5.2/24"}' $API_URL/00000000000000b3

echo -e "\n\n4. Configuring Static Routes for End-to-End Connectivity"

# sa default route to core
curl -X POST -d '{"destination": "0.0.0.0/0", "gateway": "10.10.1.2"}' $API_URL/000000000000000a

# core route to 192.168.0.x (sa)
curl -X POST -d '{"destination": "192.168.0.0/24", "gateway": "10.10.1.1"}' $API_URL/000000000000000c
# core route to 10.0.1.x (sb1) via sb
curl -X POST -d '{"destination": "10.0.1.0/24", "gateway": "10.10.2.2"}' $API_URL/000000000000000c
# core route to 10.0.2.x (sb2) via sb
curl -X POST -d '{"destination": "10.0.2.0/24", "gateway": "10.10.2.2"}' $API_URL/000000000000000c
# core route to 10.0.3.x (sb3) via sb
curl -X POST -d '{"destination": "10.0.3.0/24", "gateway": "10.10.2.2"}' $API_URL/000000000000000c

# sb route to 192.168.0.x (sa) via core
curl -X POST -d '{"destination": "192.168.0.0/24", "gateway": "10.10.2.1"}' $API_URL/000000000000000b
# sb route to 10.0.1.x (sb1) via sb1
curl -X POST -d '{"destination": "10.0.1.0/24", "gateway": "10.10.3.2"}' $API_URL/000000000000000b
# sb route to 10.0.2.x (sb2) via sb2
curl -X POST -d '{"destination": "10.0.2.0/24", "gateway": "10.10.4.2"}' $API_URL/000000000000000b
# sb route to 10.0.3.x (sb3) via sb3
curl -X POST -d '{"destination": "10.0.3.0/24", "gateway": "10.10.5.2"}' $API_URL/000000000000000b

# sb1 default route to sb
curl -X POST -d '{"destination": "0.0.0.0/0", "gateway": "10.10.3.1"}' $API_URL/00000000000000b1
# sb1 route to 10.0.2.x (sb2) via sb
curl -X POST -d '{"destination": "10.0.2.0/24", "gateway": "10.10.3.1"}' $API_URL/00000000000000b1
# sb1 route to 10.0.3.x (sb3) via sb
curl -X POST -d '{"destination": "10.0.3.0/24", "gateway": "10.10.3.1"}' $API_URL/00000000000000b1

# sb2 default route to sb
curl -X POST -d '{"destination": "0.0.0.0/0", "gateway": "10.10.4.1"}' $API_URL/00000000000000b2
# sb2 route to 192.168.0.x (sa) via sb
curl -X POST -d '{"destination": "192.168.0.0/24", "gateway": "10.10.4.1"}' $API_URL/00000000000000b2
# sb2 route to 10.0.1.x (sb1) via sb
curl -X POST -d '{"destination": "10.0.1.0/24", "gateway": "10.10.4.1"}' $API_URL/00000000000000b2
# sb2 route to 10.0.3.x (sb3) via sb
curl -X POST -d '{"destination": "10.0.3.0/24", "gateway": "10.10.4.1"}' $API_URL/00000000000000b2

# sb3 default route to sb
curl -X POST -d '{"destination": "0.0.0.0/0", "gateway": "10.10.5.1"}' $API_URL/00000000000000b3
# sb3 route to 192.168.0.x (sa) via sb
curl -X POST -d '{"destination": "192.168.0.0/24", "gateway": "10.10.5.1"}' $API_URL/00000000000000b3
# sb3 route to 10.0.1.x (sb1) via sb
curl -X POST -d '{"destination": "10.0.1.0/24", "gateway": "10.10.5.1"}' $API_URL/00000000000000b3
# sb3 route to 10.0.2.x (sb2) via sb
curl -X POST -d '{"destination": "10.0.2.0/24", "gateway": "10.10.5.1"}' $API_URL/00000000000000b3

echo -e "\n\nRouting Configuration Complete!"
