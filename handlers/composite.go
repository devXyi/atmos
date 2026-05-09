package handlers

import (
	"encoding/json"
	"io"
	"net/http"
	"time"

	"github.com/gin-gonic/gin"
)

// ─── Satellite ────────────────────────────────────────────────────────────────

func GetActiveFires(c *gin.Context) { proxyToEngine(c, "/satellite/fires") }
func GetSmokeData(c *gin.Context)   { proxyToEngine(c, "/satellite/smoke") }

// ─── Alerts ───────────────────────────────────────────────────────────────────

func GetActiveAlerts(c *gin.Context) { proxyToEngine(c, "/alerts/active") }
func GetAlertHistory(c *gin.Context) { proxyToEngine(c, "/alerts/history") }

// ─── Analytics ────────────────────────────────────────────────────────────────

func GetAQITrend(c *gin.Context)        { proxyToEngine(c, "/analytics/aqi-trend") }
func GetHealthRisk(c *gin.Context)      { proxyToEngine(c, "/analytics/health-risk") }
func GetPollutionSources(c *gin.Context) { proxyToEngine(c, "/analytics/pollution-sources") }

// ─── Dashboard ────────────────────────────────────────────────────────────────

// GET /api/v1/dashboard?lat=&lon=
// Single composite call — returns everything for dashboard render in one trip
func GetDashboard(c *gin.Context) {
	lat := c.DefaultQuery("lat", "28.6139")
	lon := c.DefaultQuery("lon", "77.2090")

	fetch := func(path string) interface{} {
		url := dataEngineURL + path + "?lat=" + lat + "&lon=" + lon
		resp, err := httpClient.Get(url)
		if err != nil {
			return nil
		}
		defer resp.Body.Close()
		body, _ := io.ReadAll(resp.Body)
		var out interface{}
		_ = json.Unmarshal(body, &out)
		return out
	}

	c.JSON(http.StatusOK, gin.H{
		"meta": gin.H{
			"lat":       lat,
			"lon":       lon,
			"timestamp": time.Now().UTC(),
			"source":    "Prexus Atmos v1",
		},
		"weather":     fetch("/weather/current"),
		"aqi":         fetch("/aqi/current"),
		"fires":       fetch("/satellite/fires"),
		"alerts":      fetch("/alerts/active"),
		"health_risk": fetch("/analytics/health-risk"),
	})
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

func readJSON(resp *http.Response, out interface{}) error {
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return err
	}
	return json.Unmarshal(body, out)
}
