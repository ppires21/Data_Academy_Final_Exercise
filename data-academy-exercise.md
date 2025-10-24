# Data Academy Final Exercise: E-Commerce Analytics Pipeline

## Overview
You will build a data pipeline for a fictional e-commerce company "ShopFlow" that needs to analyze customer behavior, product performance, and operational metrics. This exercise is divided into iterations that build upon each other, increasing in complexity.

**Duration:** 2 days  
**Submission:** ZIP file containing all code, configuration files, and documentation

---

## Initial Setup Requirements

### AWS Resources Available
- S3 buckets for raw data and processed data
- RDS PostgreSQL instance
- AWS Glue (optional for advanced iterations)
- CloudWatch for monitoring
- IAM roles with appropriate permissions

### Provided Data
You will simulate/generate e-commerce data including:
- Customer transactions
- Product catalog
- Customer profiles
- Website clickstream events

---

## Iteration 1: Foundation (Basic - 4 hours)
**Objective:** Demonstrate basic Python, SQL, and data handling skills

### Tasks:
1. **Data Generation Script** (`src/data_generator.py`)
   - Create a Python script that generates synthetic e-commerce data:
     - 1000 customers with profiles (id, name, email, registration_date, country)
     - 500 products (id, name, category, price, supplier)
     - 5000 transactions (id, customer_id, product_id, quantity, timestamp, payment_method)
   - Save as CSV files in `data/raw/` directory

2. **Data Validation** (`src/data_validator.py`)
   - Implement basic data quality checks:
     - Check for null values
     - Validate email formats
     - Ensure prices are positive
     - Check date formats
   - Log validation results to `logs/validation.log`

3. **Basic SQL Analytics** (`sql/basic_analytics.sql`)
   - Write SQL queries to answer:
     - Top 10 customers by total spending
     - Best-selling products by category
     - Monthly revenue trends
     - Average order value by country

### Deliverables:
- Python scripts with proper error handling
- SQL file with documented queries
- Sample output files
- Basic README documenting how to run the scripts

---

## Iteration 2: Database & Cloud Integration (Intermediate - 4 hours)
**Objective:** Demonstrate database management and AWS integration

### Tasks:
1. **Database Setup** (`scripts/db_setup.py`)
   - Create database schema using SQLAlchemy or psycopg2
   - Design normalized tables with proper relationships
   - Implement indexes for query optimization
   - Create views for common analytics queries

2. **Data Loading Pipeline** (`src/etl/load_to_db.py`)
   - Load generated data into PostgreSQL RDS
   - Implement upsert logic to handle duplicates
   - Add data versioning with timestamps
   - Create audit table for tracking loads

3. **S3 Integration** (`src/cloud/s3_handler.py`)
   - Upload raw CSV files to S3 with organized folder structure:
     ```
     s3://your-bucket/
     ├── raw/
     │   ├── year=2024/month=01/day=15/
     │   │   ├── customers/
     │   │   ├── products/
     │   │   └── transactions/
     ```
   - Implement file versioning
   - Add retry logic for failed uploads

4. **Configuration Management** (`config/`)
   - Create environment-specific config files (dev, prod)
   - Use environment variables for sensitive data
   - Implement config validation

### Deliverables:
- Database DDL scripts
- ETL pipeline with logging
- S3 bucket structure documentation
- Configuration templates

---

## Iteration 3: ETL & Data Transformation (Intermediate+ - 4 hours)
**Objective:** Build comprehensive ETL pipeline with transformations

### Tasks:
1. **Advanced ETL Pipeline** (`src/etl/transform_pipeline.py`)
   - Extract data from multiple sources (CSV, Database, S3)
   - Transform data:
     - Calculate customer lifetime value (CLV)
     - Create product recommendation features
     - Aggregate daily/weekly/monthly metrics
     - Handle slowly changing dimensions (SCD Type 2)
   - Load to data warehouse schema (star/snowflake)

2. **Data Quality Framework** (`src/quality/`)
   - Implement Great Expectations or custom validation:
     - Define expectation suites
     - Create data quality reports
     - Set up alerting for quality issues
   - Document data lineage

3. **Incremental Processing** (`src/etl/incremental_loader.py`)
   - Implement CDC (Change Data Capture) logic
   - Process only new/modified records
   - Maintain processing checkpoints
   - Handle late-arriving data

### Deliverables:
- Complete ETL pipeline documentation
- Data quality reports
- Performance metrics (processing time, records processed)
- Data dictionary

---

## Iteration 4: Orchestration & DevOps (Advanced - 6 hours)
**Objective:** Implement production-ready pipeline with DevOps practices

### Tasks:
1. **Workflow Orchestration** (`dags/` or `workflows/`)
   - Create Apache Airflow DAG or Step Functions workflow:
     - Daily batch processing
     - Data quality checks
     - Notification on failure
     - Retry logic and backfill capability
   - Schedule and monitor pipeline execution

2. **CI/CD Pipeline** (`.github/workflows/` or `jenkins/`)
   - Implement GitHub Actions workflow:
     - Automated testing (unit and integration)
     - Code quality checks (pylint, black)
     - Security scanning
     - Automated deployment to AWS
   - Version tagging and release notes

3. **Infrastructure as Code** (`infrastructure/`)
   - Create Terraform or CloudFormation templates:
     - S3 buckets with lifecycle policies
     - RDS instance configuration
     - IAM roles and policies
     - CloudWatch alarms
   - Environment separation (dev/staging/prod)

4. **Monitoring & Alerting** (`monitoring/`)
   - Set up CloudWatch dashboards
   - Create custom metrics for pipeline performance
   - Implement alerting for:
     - Pipeline failures
     - Data quality issues
     - Performance degradation
   - Create runbook documentation

### Deliverables:
- Complete CI/CD pipeline
- IaC templates
- Monitoring dashboards screenshots
- Deployment guide

---

## Iteration 5: Advanced Analytics & Optimization (Expert - 6 hours)
**Objective:** Implement advanced data engineering patterns

### Tasks:
1. **Stream Processing** (`src/streaming/`)
   - Simulate real-time clickstream data
   - Process using Kinesis or Kafka
   - Implement windowed aggregations
   - Create real-time dashboards

2. **Data Lake Architecture** (`src/lake/`)
   - Implement medallion architecture (Bronze/Silver/Gold)
   - Use Parquet format with partitioning
   - Implement data compaction
   - Create Apache Iceberg tables (optional)

3. **Performance Optimization** (`src/optimization/`)
   - Implement parallel processing
   - Optimize SQL queries with explain plans
   - Implement caching strategies
   - Create performance benchmarks

4. **ML Feature Engineering** (`src/features/`)
   - Create feature store
   - Implement feature pipelines
   - Version control for features
   - Create training datasets

### Deliverables:
- Streaming pipeline documentation
- Performance comparison reports
- Feature catalog
- Architecture diagrams

---

## Bonus Challenges (Optional)

1. **Data Governance**
   - Implement data catalog with AWS Glue
   - Create data classification policies
   - Implement PII detection and masking

2. **Cost Optimization**
   - Analyze and optimize AWS costs
   - Implement S3 lifecycle policies
   - Use spot instances where appropriate

3. **Advanced Security**
   - Implement encryption at rest and in transit
   - Create VPC endpoints for private connectivity
   - Implement secrets management with AWS Secrets Manager

---

## Submission Requirements

### ZIP File Structure:
```
shopflow-pipeline/
├── README.md (main documentation)
├── requirements.txt
├── .env.example
├── src/
│   ├── __init__.py
│   ├── data_generator.py
│   ├── etl/
│   ├── cloud/
│   ├── quality/
│   └── streaming/
├── sql/
│   ├── ddl/
│   └── analytics/
├── config/
│   ├── dev.yaml
│   └── prod.yaml
├── tests/
│   ├── unit/
│   └── integration/
├── infrastructure/
│   └── terraform/
├── .github/
│   └── workflows/
├── docs/
│   ├── architecture.md
│   ├── deployment.md
│   └── runbook.md
├── notebooks/ (optional Jupyter notebooks for analysis)
└── logs/ (sample logs)
```

### README.md Must Include:
1. **Project Overview** - Brief description of what was implemented
2. **Architecture Diagram** - Visual representation of the pipeline
3. **Setup Instructions** - Step-by-step guide to run the project
4. **Iterations Completed** - Clear indication of which iterations were attempted
5. **Technologies Used** - List of all tools and libraries
6. **Challenges & Solutions** - Document any issues faced and how they were resolved
7. **Performance Metrics** - Processing times, data volumes handled
8. **Future Improvements** - What could be enhanced given more time
9. **Learning Reflections** - Key takeaways from the exercise

### External Elements to Document:
- Git repository URL (if using GitHub)
- AWS resource ARNs used
- Database connection details (sanitized)
- CI/CD pipeline URLs
- Monitoring dashboard links
- Any external documentation or wikis created

---

## Evaluation Criteria

### Per Iteration:
- **Code Quality** (25%)
  - Clean, readable, and documented code
  - Proper error handling
  - Following Python best practices (PEP 8)

- **Functionality** (30%)
  - Meeting requirements
  - Correct implementation
  - Handling edge cases

- **Architecture** (20%)
  - Scalable design
  - Proper separation of concerns
  - Use of appropriate design patterns

- **DevOps Practices** (15%)
  - Version control usage
  - Testing implementation
  - Documentation quality

- **Innovation** (10%)
  - Creative solutions
  - Performance optimizations
  - Going beyond requirements

### Minimum Viable Submission:
- Complete Iteration 1 with working code and basic documentation
- This demonstrates fundamental understanding of Python, SQL, and data handling

### Expected Progression:
- **Junior Level:** Iterations 1-2
- **Mid Level:** Iterations 1-3
- **Senior Level:** Iterations 1-4
- **Expert Level:** All iterations including bonus challenges

---

## Tips for Success

1. **Start Simple:** Get Iteration 1 working completely before moving on
2. **Document as You Go:** Don't leave documentation for the end
3. **Test Frequently:** Verify each component works before integration
4. **Use Version Control:** Commit frequently with meaningful messages
5. **Ask for Help:** If stuck for more than 30 minutes, reach out to instructors
6. **Time Management:** Allocate time roughly as indicated for each iteration
7. **Focus on Quality:** Better to complete fewer iterations well than rush through all

---

## Support Resources

- AWS Documentation: Focus on S3, RDS, Glue, and CloudWatch
- Python Libraries: pandas, boto3, sqlalchemy, great-expectations
- DevOps Tools: GitHub Actions, Terraform, Docker
- Monitoring: CloudWatch, Grafana (optional)

Remember: The goal is to demonstrate your understanding and ability to apply the concepts learned during the academy. Quality over quantity!

Good luck! 🚀