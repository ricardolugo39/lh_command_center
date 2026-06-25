from app.pipelines.customer_dimension_pipeline import CustomerDimensionPipeline


if __name__ == "__main__":
    CustomerDimensionPipeline().run()
    print("✅ Customer Dimension Pipeline completed")