# Anolis 🦎

Anolis is a control runtime for machines built from many devices.

It runs on the computer that controls a machine, such as a Raspberry Pi in a
lab rig. Each piece of hardware is reached through a provider: a separate
program that talks to the device and speaks the Anolis Device Provider Protocol
(ADPP) to the runtime. The runtime discovers the devices, polls their signals,
and is the single path for control, from an HTTP API or a behavior tree.

- Docs: <https://anolishq.github.io/>
- Try it without hardware:
  [simulator quickstart](https://anolishq.github.io/repos/anolis/quickstart-simulator)

## Repositories

- [anolis](https://github.com/anolishq/anolis): the runtime, with its HTTP API and `install.sh`
- [anolis-protocol](https://github.com/anolishq/anolis-protocol): ADPP and its conformance tests
- [anolis-provider-sdk](https://github.com/anolishq/anolis-provider-sdk): C++ library the providers are built on
- [anolis-provider-sim](https://github.com/anolishq/anolis-provider-sim): simulated devices
- [anolis-provider-bread](https://github.com/anolishq/anolis-provider-bread): provider for BREAD boards on the CRUMBS I2C bus
- [anolis-provider-ezo](https://github.com/anolishq/anolis-provider-ezo): provider for Atlas Scientific EZO sensor circuits over I2C
- [anolis-workbench](https://github.com/anolishq/anolis-workbench): app to compose, provision and operate a machine
- [anolis-telemetry-export](https://github.com/anolishq/anolis-telemetry-export): exports the runtime's telemetry from InfluxDB
- [anolis-projects](https://github.com/anolishq/anolis-projects): machine configurations for specific deployments
- [fluxgraph](https://github.com/anolishq/fluxgraph): C++ signal-graph simulation library that provider-sim can use

The BREAD board firmware, the CRUMBS bus library, the BREAD contracts and the
`ezo-driver` library the EZO provider builds on are developed in
[FEAST](https://github.com/feastorg).
