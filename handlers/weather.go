package handlers

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"strconv"
	"time"

	"github.com/gin-gonic/gin"
)

var dataEngineURL = func() string {
	if u := os.Getenv("DATA_ENGINE_URL"); u != "" {
		return u
	}
	return "http://localhost:8000"
}()

var httpClient = &http.Client{Timeout: 15 * time.Second}

func proxyToEngine(c *gin.Context, path string) {
	lat := c.DefaultQuery("lat", "28.6139")
	lon := c.DefaultQuery("lon", "77.2090")

	url := fmt.Sprintf("%s%s?lat=%s&lon=%s", dataEngineURL, path, lat, lon)

	// Forward additional query params
	for k, v := range c.Request.URL.Query() {
		if k != "lat" && k != "lon" {
			url += fmt.Sprintf("&%s=%s", k, v[0])
		}
	}

	resp, err := httpClient.Get(url)
	if err != nil {
		c.JSON(http.StatusBadGateway, gin.H{"error": "data_engine_unavailable", "detail": err.Error()})
		return
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "read_error"})
		return
	}

	var result interface{}
	if err := json.Unmarshal(body, &result); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "parse_error", "raw": string(body)})
		return
	}

	c.JSON(resp.StatusCode, result)
}

// GET /api/v1/weather/current?lat=&lon=
func GetCurrentWeather(c *gin.Context) {
	proxyToEngine(c, "/weather/current")
}

// GET /api/v1/weather/forecast?lat=&lon=&days=7
func GetWeatherForecast(c *gin.Context) {
	days := c.DefaultQuery("days", "7")
	if d, err := strconv.Atoi(days); err != nil || d < 1 || d > 16 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "days must be 1–16"})
		return
	}
	proxyToEngine(c, "/weather/forecast")
}

// GET /api/v1/weather/hourly?lat=&lon=&hours=24
func GetHourlyWeather(c *gin.Context) {
	proxyToEngine(c, "/weather/hourly")
}
