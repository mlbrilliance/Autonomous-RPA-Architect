"""HTTP and JSON activity generators for UiPath XAML.

Generators for HTTP Request and Deserialize JSON activities.
"""

from __future__ import annotations

from rpa_architect.generators.base import indent, quote_attr, unique_id
from rpa_architect.generators.registry import register_generator


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------

def gen_http_request(
    url: str,
    method: str = "GET",
    body: str = "",
    headers: dict | None = None,
    output: str = "",
    display_name: str = "HTTP Request",
) -> str:
    """Generate ``<ui:HttpClient>`` activity XAML.

    Parameters
    ----------
    url:
        The request URL.
    method:
        HTTP method (``GET``, ``POST``, ``PUT``, ``DELETE``, ``PATCH``).
    body:
        Request body string (typically for POST/PUT).
    headers:
        Optional dict of header name to value.
    output:
        Variable to store the response body.
    """
    ref = unique_id()
    out_attr = f' Result="[{quote_attr(output)}]"' if output else ""
    body_attr = f' Body="{quote_attr(body)}"' if body else ""

    header_parts: list[str] = []
    if headers:
        for h_name, h_value in headers.items():
            header_parts.append(
                f'      <ui:HttpHeader Name="{quote_attr(h_name)}"'
                f' Value="{quote_attr(h_value)}" />'
            )

    if header_parts:
        headers_xml = "\n".join(header_parts)
        return (
            f'<ui:HttpClient Method="{quote_attr(method)}"'
            f' EndPoint="{quote_attr(url)}"'
            f'{body_attr}'
            f'{out_attr}'
            f' AcceptFormat="JSON"'
            f' TimeoutMS="30000"'
            f' DisplayName="{quote_attr(display_name)}"'
            f' sap2010:WorkflowViewState.IdRef="HttpClient_{ref}">\n'
            f'  <ui:HttpClient.Headers>\n'
            f'    <scg:List x:TypeArguments="ui:HttpHeader">\n'
            f'{headers_xml}\n'
            f'    </scg:List>\n'
            f'  </ui:HttpClient.Headers>\n'
            f'</ui:HttpClient>'
        )
    else:
        return (
            f'<ui:HttpClient Method="{quote_attr(method)}"'
            f' EndPoint="{quote_attr(url)}"'
            f'{body_attr}'
            f'{out_attr}'
            f' AcceptFormat="JSON"'
            f' TimeoutMS="30000"'
            f' DisplayName="{quote_attr(display_name)}"'
            f' sap2010:WorkflowViewState.IdRef="HttpClient_{ref}" />'
        )


def gen_deserialize_json(
    json_string: str,
    output: str,
    type_argument: str = "JObject",
    display_name: str = "Deserialize JSON",
) -> str:
    """Generate ``<ui:DeserializeJson>`` activity XAML.

    Parameters
    ----------
    json_string:
        Expression or variable containing the JSON string.
    output:
        Variable to store the deserialized object.
    type_argument:
        Target type (``JObject``, ``JArray``, or a custom type).
    """
    ref = unique_id()
    return (
        f'<ui:DeserializeJson x:TypeArguments="{quote_attr(type_argument)}"'
        f' JsonString="[{quote_attr(json_string)}]"'
        f' JsonObject="[{quote_attr(output)}]"'
        f' DisplayName="{quote_attr(display_name)}"'
        f' sap2010:WorkflowViewState.IdRef="DeserializeJson_{ref}" />'
    )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

register_generator("http_request", gen_http_request, "HTTP Request",
                   "HTTP / JSON", "Make an HTTP request (GET, POST, etc.)")
register_generator("deserialize_json", gen_deserialize_json, "Deserialize JSON",
                   "HTTP / JSON", "Deserialize a JSON string into a typed object")
