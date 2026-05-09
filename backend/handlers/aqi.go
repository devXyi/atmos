package handlers

import (
	"github.com/gin-gonic/gin"
)

// GET /api/v1/aqi/current?lat=&lon=
func GetCurrentAQI(c *gin.Context) {
	proxyToEngine(c, "/aqi/current")
}

// GET /api/v1/aqi/forecast?lat=&lon=&hours=72
func GetAQIForecast(c *gin.Context) {
	proxyToEngine(c, "/aqi/forecast")
}

// GET /api/v1/aqi/stations?lat=&lon=&radius=25000
func GetNearbyStations(c *gin.Context) {
	proxyToEngine(c, "/aqi/stations")
}

// GET /api/v1/aqi/heatmap?lat=&lon=&radius=&resolution=
// Returns a grid of AQI readings for heatmap rendering
func GetAQIHeatmap(c *gin.Context) {
	proxyToEngine(c, "/aqi/heatmap")
}
