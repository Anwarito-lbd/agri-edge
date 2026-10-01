// ChirpStack v4 payload codec for agri-edge field nodes.
// Byte layout: ground_iot/lorawan/PAYLOAD.md. Must agree with
// firmware/agriedge_payload.c and agri_edge.iot.lorawan (tests/test_lorawan.py).
// Output keys are the MQTT contract's (docs/MQTT_CONTRACT.md).

function u16(b, i) { return (b[i] << 8) | b[i + 1]; }
function i16(b, i) { var v = u16(b, i); return v & 0x8000 ? v - 0x10000 : v; }
function scaled(v, missing, k) { return v === missing ? null : v / k; }
function pct(v) { return v === 0xff ? null : v; }

function decodeUplink(input) {
  var b = input.bytes;
  if (!b || b.length < 2 || b[0] !== 1) {
    return { errors: ["unsupported payload version"] };
  }
  if (input.fPort === 1) {
    var n = b[2];
    if (b.length !== 3 + 5 * n) return { errors: ["soil payload length mismatch"] };
    var depths = [];
    for (var k = 0; k < n; k++) {
      var p = 3 + 5 * k;
      depths.push({
        depth_cm: b[p],
        moisture_pct: scaled(u16(b, p + 1), 0xffff, 10),
        temp_c: scaled(i16(b, p + 3), 0x7fff, 10),
      });
    }
    return { data: { kind: "soil", battery_pct: pct(b[1]), depths: depths } };
  }
  if (input.fPort === 2) {
    if (b.length !== 16) return { errors: ["weather payload length mismatch"] };
    return {
      data: {
        kind: "weather",
        battery_pct: pct(b[1]),
        air_temp_c: scaled(i16(b, 2), 0x7fff, 10),
        rh_pct: b[4] === 0xff ? null : b[4] / 2,
        pressure_hpa: scaled(u16(b, 5), 0xffff, 10),
        wind_ms: scaled(u16(b, 7), 0xffff, 10),
        wind_dir_deg: scaled(u16(b, 9), 0xffff, 1),
        precip_mm: scaled(u16(b, 11), 0xffff, 10),
        solar_wm2: scaled(u16(b, 13), 0xffff, 1),
      },
    };
  }
  return { errors: ["unknown fPort " + input.fPort] };
}

if (typeof module !== "undefined") module.exports = { decodeUplink: decodeUplink };
