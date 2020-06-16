# RbRy Oven Control Software

This repo has the currently used software for controlling the RbRy oven.
The software consists of a backend, written in Python, and a web frontend written in html.
The backend is meant to be run on a Raspberry Pi and is basically just a bottle server which takes REST commands to change/report things about the oven (set temperature, current temperature, alarms etc.), along with a simple on/off PID which tries to regulate the oven temperature.
The frontend provides a non-terrible way of interfacing with the backend.

We have been running this using nginx to host the frontend, while the backend is run as a service using the provided .service file.