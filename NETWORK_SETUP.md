# Network setup checklist

On laptops 1–5:

1. Put all laptops on the same Wi-Fi/hotspot.
2. Find each laptop's LAN IPv4 address.
3. Configure MySQL to accept LAN connections.
4. Run that laptop's `coordinator_user.sql`.
5. Allow TCP port 3306 in the firewall.
6. From the Coordinator test:

```bash
mysql -h LAPTOP_IP -u coordinator -p DATABASE_NAME -e "SHOW TABLES;"
```

The uploaded project guide uses port 3306 and recommends a dedicated `coordinator` account rather
than using root remotely.

For a production system, use TLS/encrypted database traffic, narrower firewall rules, secrets
management, retries/timeouts, authentication, and service discovery.
