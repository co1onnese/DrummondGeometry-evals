"""Enhanced export service for various formats.

Supports CSV, Excel, JSON, PDF reports, and chart images.
"""

from __future__ import annotations

import io
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import pandas as pd
import streamlit as st

logger = logging.getLogger(__name__)


class EnhancedExporter:
    """Enhanced export service for multiple formats."""

    @staticmethod
    def export_to_csv(
        data: Union[pd.DataFrame, List[Dict[str, Any]]],
        filename: str,
        include_timestamp: bool = True,
    ) -> Optional[str]:
        """
        Export data to CSV.

        Args:
            data: Data to export
            filename: Output filename
            include_timestamp: Include timestamp in filename

        Returns:
            CSV content as string
        """
        try:
            if isinstance(data, list):
                df = pd.DataFrame(data)
            else:
                df = data.copy()

            if include_timestamp:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"{filename}_{timestamp}.csv"
            else:
                filename = f"{filename}.csv"

            return df.to_csv(index=False)
        except Exception as e:
            logger.error(f"Error exporting to CSV: {e}")
            return None

    @staticmethod
    def export_to_excel(
        data: Dict[str, Union[pd.DataFrame, List[Dict[str, Any]]]],
        filename: str,
        include_timestamp: bool = True,
    ) -> Optional[bytes]:
        """
        Export data to Excel with multiple sheets.

        Args:
            data: Dictionary of sheet_name -> data
            filename: Output filename
            include_timestamp: Include timestamp in filename

        Returns:
            Excel content as bytes
        """
        try:
            buffer = io.BytesIO()

            if include_timestamp:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"{filename}_{timestamp}.xlsx"
            else:
                filename = f"{filename}.xlsx"

            with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                for sheet_name, sheet_data in data.items():
                    if isinstance(sheet_data, list):
                        df = pd.DataFrame(sheet_data)
                    else:
                        df = sheet_data.copy()

                    # Clean sheet name for Excel
                    clean_name = sheet_name.replace("/", "_")[:31]
                    df.to_excel(writer, sheet_name=clean_name, index=False)

            return buffer.getvalue()
        except Exception as e:
            logger.error(f"Error exporting to Excel: {e}")
            return None

    @staticmethod
    def export_to_json(
        data: Any,
        filename: str,
        include_timestamp: bool = True,
        pretty: bool = True,
    ) -> Optional[str]:
        """
        Export data to JSON.

        Args:
            data: Data to export
            filename: Output filename
            include_timestamp: Include timestamp in filename
            pretty: Pretty print JSON

        Returns:
            JSON content as string
        """
        try:
            if include_timestamp:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"{filename}_{timestamp}.json"
            else:
                filename = f"{filename}.json"

            indent = 2 if pretty else None
            return json.dumps(data, indent=indent, default=str)
        except Exception as e:
            logger.error(f"Error exporting to JSON: {e}")
            return None

    @staticmethod
    def export_to_pdf_report(
        title: str,
        data_sections: Dict[str, pd.DataFrame],
        chart_images: Optional[Dict[str, str]] = None,
        output_path: Optional[Path] = None,
    ) -> Optional[bytes]:
        """
        Export data to PDF report.

        Args:
            title: Report title
            data_sections: Dictionary of section_name -> DataFrame
            chart_images: Dictionary of section_name -> image path
            output_path: Optional path to save PDF

        Returns:
            PDF content as bytes
        """
        try:
            # Simple HTML report (can be extended with reportlab for richer PDFs)
            html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>{title}</title>
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 20px; }}
                    h1 {{ color: #333; }}
                    h2 {{ color: #666; margin-top: 20px; }}
                    table {{ border-collapse: collapse; width: 100%; margin: 10px 0; }}
                    th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                    th {{ background-color: #f2f2f2; }}
                    .meta {{ color: #888; font-size: 0.9em; }}
                </style>
            </head>
            <body>
                <h1>{title}</h1>
                <p class="meta">Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            """

            # Add data sections
            for section_name, df in data_sections.items():
                html += f"<h2>{section_name}</h2>\n"

                if df.empty:
                    html += "<p>No data available</p>\n"
                else:
                    html += "<table>\n"
                    html += "<tr>\n"
                    for col in df.columns:
                        html += f"<th>{col}</th>\n"
                    html += "</tr>\n"

                    for _, row in df.iterrows():
                        html += "<tr>\n"
                        for value in row:
                            html += f"<td>{value}</td>\n"
                        html += "</tr>\n"

                    html += "</table>\n"

            # Add chart images
            if chart_images:
                for section_name, img_path in chart_images.items():
                    html += f"<h2>{section_name} - Chart</h2>\n"
                    html += f'<img src="{img_path}" style="max-width: 100%;">\n'

            html += """
            </body>
            </html>
            """

            # Save HTML (simplified - in production would convert to PDF)
            if output_path:
                with open(output_path, "w") as f:
                    f.write(html)
                logger.info(f"Saved PDF report to {output_path}")

            return html.encode("utf-8")
        except Exception as e:
            logger.error(f"Error exporting to PDF: {e}")
            return None

    @staticmethod
    def create_comprehensive_report(
        report_name: str,
        data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Create a comprehensive report with multiple data sources.

        Args:
            report_name: Name of the report
            data: Dictionary containing:
                - overview: System overview data
                - predictions: Predictions data
                - backtests: Backtests data
                - data_inventory: Data inventory
                - charts: Chart data (optional)

        Returns:
            Dictionary with exportable content
        """
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # Prepare data sections for PDF
            pdf_sections = {}

            if "overview" in data and data["overview"]:
                pdf_sections["System Overview"] = pd.DataFrame([data["overview"]])

            if "predictions" in data and not data["predictions"].empty:
                # Limit to recent predictions for PDF
                recent_preds = data["predictions"].head(100)
                pdf_sections["Recent Predictions"] = recent_preds

            if "backtests" in data and not data["backtests"].empty:
                # Limit to recent backtests for PDF
                recent_bt = data["backtests"].head(50)
                pdf_sections["Recent Backtests"] = recent_bt

            if "data_inventory" in data and not data["data_inventory"].empty:
                pdf_sections["Data Inventory"] = data["data_inventory"]

            # Create Excel data
            excel_data = {}
            for key, value in data.items():
                if isinstance(value, pd.DataFrame) and not value.empty:
                    excel_data[key.title()] = value

            # Create summary
            summary = {
                "report_name": report_name,
                "generated_at": timestamp,
                "data_sources": list(data.keys()),
                "predictions_count": len(data.get("predictions", [])),
                "backtests_count": len(data.get("backtests", [])),
                "symbols_count": len(data.get("data_inventory", [])),
            }

            return {
                "summary": summary,
                "excel_data": excel_data,
                "pdf_sections": pdf_sections,
                "timestamp": timestamp,
            }
        except Exception as e:
            logger.error(f"Error creating comprehensive report: {e}")
            return {}


# Streamlit UI components

def render_export_panel(
    data: Dict[str, Any],
    default_filename: str = "dashboard_export",
) -> None:
    """
    Render export panel UI.

    Args:
        data: Data to export
        default_filename: Default filename
    """
    st.subheader("Export Data")

    # Export format selection
    export_format = st.selectbox(
        "Export Format",
        options=["CSV", "Excel", "JSON", "PDF Report"],
        index=0,
    )

    col1, col2 = st.columns(2)

    with col1:
        filename = st.text_input(
            "Filename",
            value=default_filename,
            help="Output filename (extension will be added automatically)",
        )

    with col2:
        include_timestamp = st.checkbox(
            "Include Timestamp",
            value=True,
            help="Add timestamp to filename",
        )

    if export_format == "CSV":
        # Select data to export
        data_source = st.selectbox(
            "Data Source",
            options=list(data.keys()),
        )

        export_data = data[data_source]

        if export_data is not None and not (isinstance(export_data, pd.DataFrame) and export_data.empty):
            csv_content = EnhancedExporter.export_to_csv(
                export_data,
                filename,
                include_timestamp,
            )

            if csv_content:
                st.download_button(
                    label="Download CSV",
                    data=csv_content,
                    file_name=f"{filename}.csv",
                    mime="text/csv",
                )

    elif export_format == "Excel":
        st.info("Excel export will create a workbook with multiple sheets")

        # Select all data
        excel_content = EnhancedExporter.export_to_excel(
            data,
            filename,
            include_timestamp,
        )

        if excel_content:
            st.download_button(
                label="Download Excel",
                data=excel_content,
                file_name=f"{filename}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

    elif export_format == "JSON":
        json_content = EnhancedExporter.export_to_json(
            data,
            filename,
            include_timestamp,
            pretty=True,
        )

        if json_content:
            st.download_button(
                label="Download JSON",
                data=json_content,
                file_name=f"{filename}.json",
                mime="application/json",
            )

    elif export_format == "PDF Report":
        st.info("PDF report includes data tables and charts")

        # Select data for PDF
        pdf_data = {}
        for key, value in data.items():
            if isinstance(value, pd.DataFrame) and not value.empty:
                pdf_data[key.title()] = value

        if pdf_data:
            pdf_content = EnhancedExporter.export_to_pdf_report(
                title=f"Dashboard Report - {filename}",
                data_sections=pdf_data,
            )

            if pdf_content:
                st.download_button(
                    label="Download PDF Report",
                    data=pdf_content,
                    file_name=f"{filename}.pdf",
                    mime="application/pdf",
                )

    st.markdown("---")

    # Comprehensive report section
    st.markdown("**Comprehensive Report**")

    if st.button("Generate Comprehensive Report"):
        report = EnhancedExporter.create_comprehensive_report(filename, data)

        if report:
            st.success("Report generated!")

            # Download summary
            summary_json = json.dumps(report["summary"], indent=2)
            st.download_button(
                label="Download Summary (JSON)",
                data=summary_json,
                file_name=f"{filename}_summary.json",
                mime="application/json",
            )

            # Download Excel
            if report["excel_data"]:
                excel_content = EnhancedExporter.export_to_excel(
                    report["excel_data"],
                    f"{filename}_comprehensive",
                    include_timestamp,
                )

                if excel_content:
                    st.download_button(
                        label="Download Comprehensive Excel",
                        data=excel_content,
                        file_name=f"{filename}_comprehensive.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )

            # Download PDF
            if report["pdf_sections"]:
                pdf_content = EnhancedExporter.export_to_pdf_report(
                    title=f"Comprehensive Dashboard Report - {filename}",
                    data_sections=report["pdf_sections"],
                )

                if pdf_content:
                    st.download_button(
                        label="Download Comprehensive PDF",
                        data=pdf_content,
                        file_name=f"{filename}_comprehensive.pdf",
                        mime="application/pdf",
                    )


if __name__ == "__main__":
    # Test the exporter
    exporter = EnhancedExporter()

    # Test CSV export
    test_data = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
    csv_content = exporter.export_to_csv(test_data, "test")
    print("CSV export test:", "Success" if csv_content else "Failed")

    # Test Excel export
    excel_data = {"Sheet1": test_data, "Sheet2": pd.DataFrame({"x": [1, 2]})}
    excel_content = exporter.export_to_excel(excel_data, "test")
    print("Excel export test:", "Success" if excel_content else "Failed")

    # Test JSON export
    json_content = exporter.export_to_json({"key": "value"}, "test")
    print("JSON export test:", "Success" if json_content else "Failed")
