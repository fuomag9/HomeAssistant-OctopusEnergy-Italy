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

GET_GAS_SUPPLY_POINTS_QUERY = """
query GetGasSupplyPoints($propertyId: ID!) {
  property(id: $propertyId) {
    gasSupplyPoints {
      pdr
      isSmartMeter
    }
  }
}
"""

# consumptionValue is the cumulative meter index in m3, despite its name.
GET_GAS_READINGS_QUERY = """
query GetGasReadings($accountNumber: String!, $pdr: String!, $dateFrom: Date, $dateTo: Date) {
  gasMeterReadings(
    accountNumber: $accountNumber,
    pdr: $pdr,
    dateFrom: $dateFrom,
    dateTo: $dateTo,
    first: 100
  ) {
    edges {
      node {
        readingDate
        readingType
        consumptionValue
      }
    }
  }
}
"""


# Default refresh interval (in seconds):
DEFAULT_SCAN_INTERVAL = 3600  # 1 hour

# Gas readings arrive about once a month, so they are checked far less often.
GAS_SCAN_INTERVAL = 12 * 3600

# Days of gas readings fetched (and re-imported as statistics) on every refresh.
GAS_HISTORY_DAYS = 730

# Timezone used to align daily readings with the Italian calendar day.
TIMEZONE = "Europe/Rome"

# Days of readings fetched (and re-imported as statistics) on every refresh.
HISTORY_DAYS = 30

# Sensor types: key -> (name, unit, attribute_key)
SENSOR_TYPES = {
    "daily_total": ["Daily Total", "kWh", None],
    "daily_f1": ["Daily F1", "kWh", "F1"],
    "daily_f2": ["Daily F2", "kWh", "F2"],
    "daily_f3": ["Daily F3", "kWh", "F3"],
}