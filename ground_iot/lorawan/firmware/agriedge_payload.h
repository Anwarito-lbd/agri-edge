/*
 * agri-edge LoRaWAN uplink payloads. Byte layout: ground_iot/lorawan/PAYLOAD.md
 *
 * Big-endian, fixed-point, one byte of version first. A missing reading is
 * sent as the field's MISSING value, never as 0: a dry probe reads 0 %.
 *
 * Decoded by ground_iot/lorawan/chirpstack_codec.js (ChirpStack v4) and by
 * agri_edge.iot.lorawan (the bridge), which must agree -- tests/test_lorawan.py
 * compiles this file and checks all three against each other.
 */
#ifndef AGRIEDGE_PAYLOAD_H
#define AGRIEDGE_PAYLOAD_H

#include <stddef.h>
#include <stdint.h>

#define AE_PAYLOAD_VERSION 1
#define AE_PORT_SOIL 1
#define AE_PORT_WEATHER 2
#define AE_MAX_DEPTHS 4
#define AE_MISSING_U16 0xFFFFu
#define AE_MISSING_I16 ((int16_t)0x7FFF)
#define AE_MISSING_U8 0xFFu

typedef struct {
    uint8_t depth_cm;
    float moisture_pct;   /* NAN = missing */
    float temp_c;         /* NAN = missing */
} ae_depth_t;

/* Returns bytes written, or 0 if buf is too small / too many depths. */
size_t ae_encode_soil(uint8_t *buf, size_t cap, float battery_pct,
                      const ae_depth_t *depths, uint8_t n_depths);

size_t ae_encode_weather(uint8_t *buf, size_t cap, float battery_pct,
                         float air_temp_c, float rh_pct, float pressure_hpa,
                         float wind_ms, float wind_dir_deg, float rain_mm,
                         float solar_wm2);

#endif
