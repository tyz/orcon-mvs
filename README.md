# Orcon MVS

(Work in progress)

Home-Assistant integration for Orcon MVS-15 fan + CO₂ sensor + RF15 remote.

Uses MQTT and a [Ramses ESP stick](https://indalo-tech.onlineweb.shop/product/ramses-esp)
to communicate with the fan.

Used [ramses_rf](https://github.com/zxdavb/ramses_rf) for some code/inspiration/help.

## Lovelace

```yaml
type: tile
entity: fan.orcon_mvs_ventilation
show_entity_picture: false
hide_state: true
vertical: false
features_position: inline
features:
  - type: fan-preset-modes
    style: dropdown
```
