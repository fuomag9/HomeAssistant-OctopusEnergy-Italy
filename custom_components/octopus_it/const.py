DOMAIN = "octopus_it"

# GraphQL endpoints:
API_BASE = "https://api.oeit-kraken.energy/v1/graphql/"

LOGIN_QUERY = """
mutation Login($input: ObtainJSONWebTokenInput!) {
  obtainKrakenToken(input: $input) {
    token
    refreshToken
    refreshExpiresIn
  }
}
"""

GET_ACCOUNT_LIST_QUERY = """
query GetAccountList {
  viewer {
    accounts {
      number
      __typename
    }
  }
}
"""


GET_PROPERTIES_QUERY = """
query GetAccountProperties($accountNumber: String!) {
  account(accountNumber: $accountNumber) {
    properties {
      id
    }
  }
}
"""

GET_METERS_QUERY = """
query GetMetersForProperty($propertyId: ID!) {
  property(id: $propertyId) {
    electricitySupplyPoints {
      id
      pod
      isSmartMeter
    }
  }
}
"""

# When fetching daily usage, we ask for DAY_INTERVAL,
# and set the marketSupplyPointId dynamically from meters.
GET_SMART_USAGE_QUERY = """
query GetSmartUsage(
  $propertyId: ID!, 
  $timezone: String!, 
  $startAt: DateTime!, 
  $endAt: DateTime!, 
  $utilityFilters: [UtilityFiltersInput!]!
) {
  property(id: $propertyId) {
    measurements(
      first: 1000, 
      timezone: $timezone, 
      startAt: $startAt, 
      endAt: $endAt, 
      utilityFilters: $utilityFilters
    ) {
      edges {
        node {
          __typename
          value
          unit
          ... on IntervalMeasurementType {
            startAt
            endAt
          }
          metaData {
            utilityFilters {
              __typename
              ... on ElectricityFiltersOutput {
                readingDirection
              }
              ... on GasFiltersOutput {
                __typename
              }
            }
            statistics {
              label
              value
              type
              costInclTax {
                costCurrency
                estimatedAmount
              }
              costExclTax {
                costCurrency
                estimatedAmount
              }
            }
          }
        }
      }
    }
  }
}
"""


# Default refresh interval (in seconds):
DEFAULT_SCAN_INTERVAL = 3600  # 1 hour

# Sensor types: key -> (name, unit, attribute_key)
SENSOR_TYPES = {
    "daily_total": ["Daily Total", "kWh", None],
    "daily_f1": ["Daily F1", "kWh", "F1"],
    "daily_f2": ["Daily F2", "kWh", "F2"],
    "daily_f3": ["Daily F3", "kWh", "F3"],
}