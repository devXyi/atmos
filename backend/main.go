package main

import (
	"log"
	"net/http"
	"os"
	"time"

	"github.com/gin-contrib/cors"
	"github.com/gin-gonic/gin"
	"github.com/joho/godotenv"

	"atmos/handlers"
	"atmos/middleware"
)

func main() {
	if err := godotenv.Load(); err != nil {
		log.Println("No .env file found, using environment variables")
	}

	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	if os.Getenv("GIN_MODE") == "release" {
		gin.SetMode(gin.ReleaseMode)
	}

	r := gin.New()
	r.Use(gin.Logger())
	r.Use(gin.Recovery())

	// CORS
	r.Use(cors.New(cors.Config{
		AllowOrigins:     []string{"*"},
		AllowMethods:     []string{"GET", "POST", "OPTIONS"},
		AllowHeaders:     []string{"Origin", "Content-Type", "Authorization", "X-API-Key"},
		ExposeHeaders:    []string{"Content-Length", "X-Request-ID"},
		AllowCredentials: false,
		MaxAge:           12 * time.Hour,
	}))

	// Rate limiting middleware
	r.Use(middleware.RateLimit())

	// Health check
	r.GET("/health", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{
			"status":    "operational",
			"service":   "Prexus Atmos API Gateway",
			"version":   "1.0.0",
			"timestamp": time.Now().UTC(),
		})
	})

	api := r.Group("/api/v1")
	{
		// Weather endpoints
		weather := api.Group("/weather")
		{
			weather.GET("/current", handlers.GetCurrentWeather)
			weather.GET("/forecast", handlers.GetWeatherForecast)
			weather.GET("/hourly", handlers.GetHourlyWeather)
		}

		// AQI endpoints
		aqi := api.Group("/aqi")
		{
			aqi.GET("/current", handlers.GetCurrentAQI)
			aqi.GET("/forecast", handlers.GetAQIForecast)
			aqi.GET("/stations", handlers.GetNearbyStations)
			aqi.GET("/heatmap", handlers.GetAQIHeatmap)
		}

		// Satellite / fire data
		satellite := api.Group("/satellite")
		{
			satellite.GET("/fires", handlers.GetActiveFires)
			satellite.GET("/smoke", handlers.GetSmokeData)
		}

		// Alerts
		alerts := api.Group("/alerts")
		{
			alerts.GET("/active", handlers.GetActiveAlerts)
			alerts.GET("/history", handlers.GetAlertHistory)
		}

		// Analytics
		analytics := api.Group("/analytics")
		{
			analytics.GET("/aqi-trend", handlers.GetAQITrend)
			analytics.GET("/health-risk", handlers.GetHealthRisk)
			analytics.GET("/pollution-sources", handlers.GetPollutionSources)
		}

		// Composite endpoint — full dashboard payload in one call
		api.GET("/dashboard", handlers.GetDashboard)

		// Monitored locations — global city AQI for globe markers
		api.GET("/locations", handlers.GetMonitoredLocations)
	}

	log.Printf("Prexus Atmos API Gateway starting on :%s", port)
	if err := r.Run(":" + port); err != nil {
		log.Fatalf("Failed to start server: %v", err)
	}
}
