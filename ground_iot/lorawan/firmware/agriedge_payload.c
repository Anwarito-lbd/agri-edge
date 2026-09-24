#include "agriedge_payload.h"

#include <math.h>

static void put_u16(uint8_t *p, uint16_t v) { p[0] = (uint8_t)(v >> 8); p[1] = (uint8_t)v; }

static uint16_t scale_u16(float v, float k) {
    if (isnan(v) || v < 0.0f) return AE_MISSING_U16;
    float s = roundf(v * k);
    return s >= 65535.0f ? (uint16_t)65534u : (uint16_t)s;
}

static int16_t scale_i16(float v, float k) {
    if (isnan(v)) return AE_MISSING_I16;
    float s = roundf(v * k);
    if (s > 32766.0f) s = 32766.0f;
    if (s < -32768.0f) s = -32768.0f;
    return (int16_t)s;
}

static uint8_t pct_u8(float v) {
    if (isnan(v) || v < 0.0f) return AE_MISSING_U8;
    return v > 100.0f ? 100 : (uint8_t)roundf(v);
}

size_t ae_encode_soil(uint8_t *buf, size_t cap, float battery_pct,
                      const ae_depth_t *depths, uint8_t n_depths) {
    size_t need = 3u + 5u * n_depths;
    if (n_depths > AE_MAX_DEPTHS || cap < need) return 0;
    buf[0] = AE_PAYLOAD_VERSION;
    buf[1] = pct_u8(battery_pct);
    buf[2] = n_depths;
    for (uint8_t i = 0; i < n_depths; i++) {
        uint8_t *p = buf + 3 + 5 * i;
        p[0] = depths[i].depth_cm;
        put_u16(p + 1, scale_u16(depths[i].moisture_pct, 10.0f));
        put_u16(p + 3, (uint16_t)scale_i16(depths[i].temp_c, 10.0f));
    }
    return need;
}

size_t ae_encode_weather(uint8_t *buf, size_t cap, float battery_pct,
                         float air_temp_c, float rh_pct, float pressure_hpa,
                         float wind_ms, float wind_dir_deg, float rain_mm,
                         float solar_wm2) {
    if (cap < 16) return 0;
    buf[0] = AE_PAYLOAD_VERSION;
    buf[1] = pct_u8(battery_pct);
    put_u16(buf + 2, (uint16_t)scale_i16(air_temp_c, 10.0f));
    buf[4] = (isnan(rh_pct) || rh_pct < 0.0f) ? AE_MISSING_U8
             : (uint8_t)roundf((rh_pct > 100.0f ? 100.0f : rh_pct) * 2.0f);
    put_u16(buf + 5, scale_u16(pressure_hpa, 10.0f));
    put_u16(buf + 7, scale_u16(wind_ms, 10.0f));
    put_u16(buf + 9, scale_u16(wind_dir_deg, 1.0f));
    put_u16(buf + 11, scale_u16(rain_mm, 10.0f));
    put_u16(buf + 13, scale_u16(solar_wm2, 1.0f));
    buf[15] = 0;   /* reserved */
    return 16;
}
