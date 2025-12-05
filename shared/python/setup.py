from setuptools import setup, find_packages

setup(
    name="tiktok-auto-shared",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "sqlalchemy>=2.0.0",
        "psycopg2-binary>=2.9.0",
        "celery>=5.3.0",
        "redis>=5.0.0",
        "elasticsearch>=8.11.0",
        "pydantic>=2.0.0",
        "pydantic-settings>=2.0.0",
    ],
    python_requires=">=3.11",
)
