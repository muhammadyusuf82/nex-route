from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied

def get_street_data_from_lat_and_lon(lat, lon):
    geolocator = Nominatim(user_agent="Llogistix")
    reverse = RateLimiter(geolocator.reverse, min_delay_seconds=1)

    location = reverse((lat, lon), language="en", addressdetails=True)
    if not location:
        return None

    address = location.raw.get("address", {})

    street = (
        address.get("road")
        or address.get("pedestrian")
        or address.get("footway")
    )
    city = (
        address.get("city")
        or address.get("town")
        or address.get("village")
        or address.get("municipality")
    )
    region = (
        address.get("state")
        or address.get('region')
        or address.get("county")
    )

    return {
        "street": street,
        "city": city,
        "region": region
    }

@api_view(['GET'])
def get_street_data(request, lat: float, lon: float):
    if not request.user.is_superuser:
        return PermissionDenied()
    return Response(get_street_data_from_lat_and_lon(lat, lon))