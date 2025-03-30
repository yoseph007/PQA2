import os
import time
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image

class PDFCertificateGenerator:
    """Generates PDF certificate with VMAF test results"""
    
    def __init__(self):
        self.styles = getSampleStyleSheet()
        # Create custom styles
        self.styles.add(ParagraphStyle(
            name='Heading1Center',
            parent=self.styles['Heading1'],
            alignment=1,  # Center alignment
        ))
        self.styles.add(ParagraphStyle(
            name='Normal_Center',
            parent=self.styles['Normal'],
            alignment=1,  # Center alignment
        ))
        
    def generate_certificate(self, test_name, reference_path, captured_path, 
                            vmaf_results, output_path):
        """Generate a PDF certificate with test results"""
        
        doc = SimpleDocTemplate(
            output_path,
            pagesize=letter,
            rightMargin=72,
            leftMargin=72,
            topMargin=72,
            bottomMargin=72
        )
        
        # Prepare story (content elements)
        story = []
        
        # Title
        story.append(Paragraph("VMAF Test Certificate", self.styles['Heading1Center']))
        story.append(Spacer(1, 20))
        
        # Test Information
        story.append(Paragraph("Test Information", self.styles['Heading2']))
        story.append(Spacer(1, 10))
        
        # Test metadata
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        test_data = [
            ["Test Name:", test_name],
            ["Date/Time:", timestamp],
            ["Location:", "Lab A, Hitachi Connect"],  # This would be user input in a real app
            ["Operator:", "System User"],  # This would be user input in a real app
        ]
        
        test_table = Table(test_data, colWidths=[120, 300])
        test_table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('PADDING', (0, 0), (-1, -1), 6),
        ]))
        
        story.append(test_table)
        story.append(Spacer(1, 20))
        
        # Video Specifications
        story.append(Paragraph("Video Specifications", self.styles['Heading2']))
        story.append(Spacer(1, 10))
        
        # Extract video info (in real app, this would come from FFprobe)
        # This is placeholder data
        video_specs = [
            ["", "Captured Video", "Reference Video"],
            ["Resolution:", "1920x1080", "1920x1080"],
            ["Frame Rate:", "60fps", "60fps"],
            ["Duration:", "00:01:30", "00:01:30"],
            ["Total Frames:", "5400", "5400"],
        ]
        
        video_table = Table(video_specs, colWidths=[120, 150, 150])
        video_table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('BACKGROUND', (0, 1), (0, -1), colors.lightgrey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('PADDING', (0, 0), (-1, -1), 6),
        ]))
        
        story.append(video_table)
        story.append(Spacer(1, 20))
        
        # VMAF Results
        story.append(Paragraph("VMAF Analysis Results", self.styles['Heading2']))
        story.append(Spacer(1, 10))
        
        # Extract VMAF scores from results
        # In a real app, parse the actual JSON results
        vmaf_mean = vmaf_results.get('vmaf_score', 92.5)
        vmaf_min = vmaf_results.get('vmaf_min', 85.2)
        vmaf_max = vmaf_results.get('vmaf_max', 97.8)
        psnr = vmaf_results.get('psnr', 38.6)
        
        vmaf_data = [
            ["Model Used:", "vmaf_v0.6.1.json"],
            ["Overall Score:", f"{vmaf_mean:.2f}"],
            ["Minimum Score:", f"{vmaf_min:.2f}"],
            ["Maximum Score:", f"{vmaf_max:.2f}"],
            ["PSNR:", f"{psnr:.2f} dB"],
        ]
        
        vmaf_table = Table(vmaf_data, colWidths=[120, 300])
        vmaf_table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('PADDING', (0, 0), (-1, -1), 6),
        ]))
        
        story.append(vmaf_table)
        story.append(Spacer(1, 20))
        
        # Technical Notes
        story.append(Paragraph("Technical Notes", self.styles['Heading2']))
        story.append(Spacer(1, 10))
        
        notes_data = [
            ["Alignment Method:", "Auto (SSIM-based)"],
            ["Analysis Duration:", "Full video (90 seconds)"],
            ["Output Files:", f"./results/{test_name}/vmaf_results.csv\n./results/{test_name}/frame_compare/"],
        ]
        
        notes_table = Table(notes_data, colWidths=[120, 300])
        notes_table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('PADDING', (0, 0), (-1, -1), 6),
        ]))
        
        story.append(notes_table)
        story.append(Spacer(1, 30))
        
        # Certificate footer
        story.append(Paragraph(
            f"Generated by Hitachi Connect Project VMAF Test App on {timestamp}",
            self.styles['Normal_Center']
        ))
        
        # Build the PDF
        doc.build(story)
        
        return output_path