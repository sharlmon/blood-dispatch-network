"""Public interactive API documentation with bundled, locally served assets."""
from flask import Blueprint, jsonify, render_template_string
from swagger_ui_bundle import swagger_ui_path

from .openapi import build_spec

docs = Blueprint('api_docs', __name__, static_folder=swagger_ui_path, static_url_path='/docs/assets')


@docs.get('/openapi.json')
def openapi():
    return jsonify(build_spec())


@docs.get('/docs')
@docs.get('/docs/')
def swagger():
    return render_template_string('''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Blood Dispatch Network API — Swagger UI</title>
  <link rel="stylesheet" href="{{ url_for('api_docs.static', filename='swagger-ui.css') }}">
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="{{ url_for('api_docs.static', filename='swagger-ui-bundle.js') }}"></script>
  <script>
    window.onload = function () {
      window.ui = SwaggerUIBundle({
        url: {{ url_for('api_docs.openapi') | tojson }},
        dom_id: '#swagger-ui',
        deepLinking: true,
        validatorUrl: null,
        persistAuthorization: false,
        displayRequestDuration: true,
        presets: [SwaggerUIBundle.presets.apis],
        layout: 'BaseLayout'
      });
    };
  </script>
</body>
</html>''')
