# EC2 System Health Monitor

A lightweight Python-based Linux system health monitoring tool for Amazon Linux 2023 EC2 instances.

It collects CPU, memory, disk, hostname, and kernel information, evaluates the system against configurable thresholds, stores health reports and history, and sends email alerts when the health state or detected issues change.

## Features

- CPU utilization monitoring
- Memory utilization monitoring
- Disk utilization monitoring
- Configurable thresholds
- Hostname and kernel information
- HEALTHY / ISSUE / ERROR health states
- JSON health reports
- Historical health records
- Atomic JSON file writes
- Email alerting through the local `sendmail` interface
- Duplicate alert suppression
- Recovery notifications
- Command timeout protection
- Centralized command execution and error handling
- systemd service and timer
- Logrotate-compatible application log
- Runs as a non-root user
- systemd security restrictions

## Architecture

```text
systemd timer
      |
      | every 5 minutes
      v
system-health.service
      |
      v
system_infoo.py
      |
      +-- CPU
      +-- Memory
      +-- Disk
      +-- Hostname
      +-- Kernel
      |
      +-- Health evaluation
      |
      +-- JSON reports
      |
      +-- Alert state
      |
      +-- Email alert
