"""交互式地图渲染：把模型生成的 POI 列表渲染成自包含的 Leaflet HTML。

不依赖 folium/网络，直接生成 Leaflet.js 页面（Leaflet 走 CDN 引入），
每个 POI 是一个可点击的 marker，弹窗显示名称/类别/描述与坐标。
"""
from __future__ import annotations

import html
import json
from pathlib import Path

from .schemas import Marker

_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>{title}</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  html,body{{margin:0;height:100%;font-family:-apple-system,"Segoe UI",Roboto,"Microsoft YaHei",sans-serif}}
  #map{{height:100%}}
  .legend{{position:absolute;z-index:1000;right:12px;top:12px;background:rgba(255,255,255,.94);
    padding:10px 14px;border-radius:8px;box-shadow:0 2px 8px rgba(0,0,0,.15);font-size:13px;max-width:260px}}
  .legend h3{{margin:0 0 6px;font-size:14px}}
  .legend .meta{{color:#666;font-size:12px;margin-top:6px;line-height:1.5}}
  .popup-desc{{color:#444;font-size:12px}}
</style>
</head>
<body>
<div id="map"></div>
<div class="legend">
  <h3>{title}</h3>
  <div>共 <b>{count}</b> 个地点</div>
  <div class="meta">中心：{center_lat:.4f}, {center_lon:.4f}<br/>模型：{model}<br/>设备：{device}</div>
</div>
<script>
var CENTER = [{center_lat}, {center_lon}];
var MARKERS = {markers_json};
var map = L.map('map').setView(CENTER, 16);
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
  maxZoom: 19, attribution: '&copy; OpenStreetMap contributors'
}}).addTo(map);
L.circle(CENTER, {{radius: 400, color: '#2563eb', fillColor: '#3b82f6', fillOpacity: 0.08}}).addTo(map);
var bounds = [CENTER];
MARKERS.forEach(function(m) {{
  var mk = L.marker([m.lat, m.lon]).addTo(map);
  mk.bindPopup('<b>' + m.name + '</b> <span style="color:#2563eb">[' + m.category + ']</span>'
    + '<div class="popup-desc">' + (m.description || '') + '</div>'
    + '<div style="color:#999;font-size:11px">' + m.lat.toFixed(4) + ', ' + m.lon.toFixed(4) + '</div>');
  bounds.push([m.lat, m.lon]);
}});
map.fitBounds(bounds, {{padding: [40, 40]}});
</script>
</body>
</html>
"""


def render_map(
    markers: list[Marker],
    title: str,
    center: dict,
    out_path: str | Path,
    model: str = "gemma-3-1b-it",
    device: str = "cpu",
) -> Path:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    data = [m.as_dict() for m in markers]
    out.write_text(
        _TEMPLATE.format(
            title=html.escape(title),
            count=len(data),
            center_lat=center["lat"],
            center_lon=center["lon"],
            markers_json=json.dumps(data, ensure_ascii=False, indent=2),
            model=html.escape(model),
            device=html.escape(device),
        ),
        encoding="utf-8",
    )
    return out
