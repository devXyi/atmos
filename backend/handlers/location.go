package handlers

import (
	"github.com/gin-gonic/gin"
)

// GET /api/v1/locations
// Returns all monitored locations with their latest AQI snapshot.
// Used by the frontend globe to render global city markers.
func GetMonitoredLocations(c *gin.Context) {
	proxyToEngine(c, "/locations")
}
