import io
import matplotlib.pyplot as plt
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
import streamlit as st

st.set_page_config(
    page_title='DT Overloading Dashboard', page_icon='⚡', layout='wide'
)

st.title('⚡ Distribution Transformer (DT) Overloading Dashboard')
st.markdown(
    'Upload your master dataset containing multiple DTs to analyze IEC'
    ' overloading criteria, visualize graphs interactively, select custom'
    ' time slots, and export professional PDF and Excel reports.'
)

uploaded_file = st.file_uploader(
    'Upload Master CSV File (Multi-DT Data)', type=['csv']
)

if uploaded_file is not None:

  @st.cache_data
  def load_data(file):
    return pd.read_csv(file)

  df = load_data(uploaded_file)

  # Automatically find the time/date column
  possible_time_cols = [
      'Date + Time',
      'Timestamp',
      'Date_Time',
      'DateTime',
      'Date',
      'Time',
  ]
  time_col = next((col for col in possible_time_cols if col in df.columns), None)

  if time_col:
    df[time_col] = pd.to_datetime(df[time_col], errors='coerce')
  else:
    for col in df.columns:
      if 'date' in col.lower() or 'time' in col.lower():
        time_col = col
        df[time_col] = pd.to_datetime(df[time_col], errors='coerce')
        break

  # Automatically find meter/DT ID columns
  meter_col = next(
      (
          col
          for col in [
              'Meter No',
              'Meter_No',
              'MeterNo',
              'DT ID',
              'DT_ID',
          ]
          if col in df.columns
      ),
      None,
  )
  if meter_col is None:
    string_cols = df.select_dtypes(include=['object']).columns
    meter_col = string_cols[0] if len(string_cols) > 0 else df.columns[0]

  if time_col is None:
    st.error('Could not find a timestamp or date column in your dataset.')
  else:
    st.sidebar.header('Selection Filters')
    unique_meters = df[meter_col].dropna().unique()
    selected_meter = st.sidebar.selectbox(
        'Select Meter No / DT ID:', unique_meters
    )

    # --- FILTER DATA FOR SELECTED METER FIRST ---
    df_current_all = df[df[meter_col] == selected_meter].sort_values(time_col)

    # --- DATE RANGE SELECTOR ---
    if not df_current_all.empty and df_current_all[time_col].notna().any():
      min_date = df_current_all[time_col].min().date()
      max_date = df_current_all[time_col].max().date()

      st.sidebar.markdown('---')
      st.sidebar.subheader('📅 Time Slot Filter')
      selected_date_range = st.sidebar.date_input(
          'Select Date Range:',
          value=(min_date, max_date),
          min_value=min_date,
          max_value=max_date,
      )

      # Handle single date selection vs range selection
      if isinstance(selected_date_range, tuple) and len(selected_date_range) == 2:
        start_date, end_date = selected_date_range
      else:
        start_date = end_date = selected_date_range

      # Filter dataset by selected date range (inclusive of full days)
      mask = (df_current_all[time_col].dt.date >= start_date) & (
          df_current_all[time_col].dt.date <= end_date
      )
      df_current = df_current_all.loc[mask]
    else:
      start_date, end_date = None, None
      df_current = df_current_all


    # Helper function to compute analysis for any given meter dataframe subset
    def analyze_dt(df_selected, m_id):
      dt_id = str(m_id)
      meter_no = str(m_id)
      capacity = (
          str(df_selected['DTS (kVA)'].iloc[0])
          if 'DTS (kVA)' in df_selected.columns and len(df_selected) > 0
          else (
              'Capacity' in df_selected.columns
              and len(df_selected) > 0
              and str(df_selected['Capacity'].iloc[0])
              or 'N/A'
          )
      )

      lt_amps_col = next(
          (
              col
              for col in [
                  'LT Amps rated',
                  'LT_Amps_Rated',
                  'Rated Current',
              ]
              if col in df_selected.columns
          ),
          None,
      )
      limit_col = next(
          (
              col
              for col in [
                  'Limit(80% of LT Amps Rated)',
                  'Limit_80_Pct',
              ]
              if col in df_selected.columns
          ),
          None,
      )

      current_col = next(
          (
              col
              for col in ['Avg Current', 'Current', 'Avg_Current']
              if col in df.columns
          ),
          df.columns[1],
      )

      # --- SAFE NUMERIC CONVERSION ---
      df_selected = df_selected.copy()
      df_selected[current_col] = pd.to_numeric(
          df_selected[current_col], errors='coerce'
      ).fillna(0)

      if lt_amps_col and lt_amps_col in df_selected.columns:
        df_selected[lt_amps_col] = pd.to_numeric(
            df_selected[lt_amps_col], errors='coerce'
        )

      if limit_col and limit_col in df_selected.columns:
        limit_series = pd.to_numeric(
            df_selected[limit_col], errors='coerce'
        ).fillna(0)
      elif lt_amps_col and lt_amps_col in df_selected.columns:
        limit_series = df_selected[lt_amps_col].fillna(0) * 0.80
      else:
        limit_series = df_selected[current_col] * 0.80

      if lt_amps_col and lt_amps_col in df_selected.columns:
        valid_lt = df_selected[lt_amps_col].replace(0, pd.NA)
        df_selected['Loading_Pct'] = (
            df_selected[current_col] / valid_lt
        ) * 100
        df_selected['Loading_Pct'] = df_selected['Loading_Pct'].fillna(0)
      else:
        df_selected['Loading_Pct'] = 0.0

      criteria = {
          '>80%': {'threshold': 80.0, 'min_rows': 16, 'perm_dur': 480},
          '>90%': {'threshold': 90.0, 'min_rows': 8, 'perm_dur': 240},
          '>100%': {'threshold': 100.0, 'min_rows': 4, 'perm_dur': 120},
          '>110%': {'threshold': 110.0, 'min_rows': 2, 'perm_dur': 60},
          '>120%': {'threshold': 120.0, 'min_rows': 1, 'perm_dur': 30},
          '>130%': {'threshold': 130.0, 'min_rows': 1, 'perm_dur': 15},
      }

      def count_continuous_instances(series, threshold, min_rows):
        if len(series) == 0:
          return 0
        mask = series >= threshold
        block_id = (mask != mask.shift()).cumsum()
        valid_blocks = mask.groupby(block_id).agg(
            lambda x: x.all() and len(x) >= min_rows
        )
        return valid_blocks.sum()

      table_data = []
      for label, params in criteria.items():
        instances = count_continuous_instances(
            df_selected['Loading_Pct'],
            params['threshold'],
            params['min_rows'],
        )
        table_data.append([label, instances, params['perm_dur']])

      return (
          df_selected,
          dt_id,
          meter_no,
          capacity,
          limit_series,
          current_col,
          table_data,
      )


    # Run analysis on filtered date subset for current view
    (
        df_selected,
        dt_id,
        meter_no,
        capacity,
        limit_series,
        current_col,
        table_data,
    ) = analyze_dt(df_current, selected_meter)

    total_violations = sum([row[1] for row in table_data])

    # Display metrics summary cards on top
    col1, col2, col3 = st.columns(3)
    col1.metric('Selected Meter No', meter_no)
    col2.metric('DT Capacity', f'{capacity} kVA')
    col3.metric('Filtered Overloading Instances', total_violations)

    st.markdown('---')

    # Generate interactive plot (UI display)
    fig, ax = plt.subplots(figsize=(14, 7), dpi=300)
    if not df_selected.empty:
      ax.plot(
          df_selected[time_col],
          df_selected[current_col],
          color='#1f77b4',
          linewidth=0.8,
          label='Avg Loading',
      )

      avg_limit_value = limit_series.mean()
      ax.axhline(
          y=avg_limit_value,
          color='red',
          linestyle='--',
          linewidth=1.2,
          label='80% Loading',
      )

      if len(df_selected) > 0:
        ax.text(
            df_selected[time_col].iloc[int(len(df_selected) * 0.70)],
            avg_limit_value + 15,
            '80% Loading',
            color='red',
            fontsize=9,
            fontweight='bold',
        )
      ax.set_xlim(pd.to_datetime(start_date), pd.to_datetime(end_date) + pd.Timedelta(days=1))
    else:
      ax.text(
          0.5,
          0.5,
          'No data available for the selected date range',
          horizontalalignment='center',
          verticalalignment='center',
          transform=ax.transAxes,
          fontsize=12,
          color='gray',
      )

    title_str = (
        f'DT ID: {dt_id}  |  Meter No: {meter_no}  |  Capacity: {capacity}'
    )
    fig.suptitle(title_str, fontsize=11, fontweight='bold', y=0.96)
    ax.set_title(
        'DT Loading Status as per IEC OL Criteria (Filtered Range)',
        fontsize=10,
        fontweight='bold',
        pad=15,
    )

    ax.set_xlabel('Timestamp', fontsize=10, fontweight='bold')
    ax.set_ylabel('Current (Amperes)', fontsize=10, fontweight='bold')

    ax.grid(True, linestyle='--', alpha=0.5)
    ax.legend(loc='upper left')

    plt.subplots_adjust(top=0.88, bottom=0.1, left=0.08, right=0.95)
    st.pyplot(fig)

    with st.expander('View Filtered Raw Data Records for Selected DT'):
      st.dataframe(df_selected)

    st.markdown('---')


    # --- EXCEL ANALYSIS RESULTS GENERATOR (WITH ROBUST DATE FILTERING) ---
    def generate_excel_analysis_report():
      excel_rows = []
      for m in unique_meters:
        d_sub_all = df[df[meter_col] == m].sort_values(time_col)
        if start_date and end_date and not d_sub_all.empty:
          mask_ex = (d_sub_all[time_col].dt.date >= start_date) & (
              d_sub_all[time_col].dt.date <= end_date
          )
          d_sub = d_sub_all.loc[mask_ex]
        else:
          d_sub = d_sub_all

        _, _, m_no, _, _, _, t_data = analyze_dt(d_sub, m)
        
        row_dict = {'Meter_No': m_no}
        inst_80 = t_data[0][1]
        inst_90 = t_data[1][1]
        inst_100 = t_data[2][1]
        inst_110 = t_data[3][1]
        inst_120 = t_data[4][1]
        inst_130 = t_data[5][1]
        total_ol = inst_80 + inst_90 + inst_100 + inst_110 + inst_120 + inst_130

        row_dict['Above 80% for 480 min'] = inst_80
        row_dict['Above 90% for 240 min'] = inst_90
        row_dict['Above 100% for 120 min'] = inst_100
        row_dict['Above 110% for 60 min'] = inst_110
        row_dict['Above 120% for 30 min'] = inst_120
        row_dict['Above 130% for 15 min'] = inst_130
        row_dict['Total IEC OL Instances'] = total_ol

        excel_rows.append(row_dict)

      summary_df = pd.DataFrame(excel_rows)
      
      output = io.BytesIO()
      with pd.ExcelWriter(output, engine='openpyxl') as writer:
        summary_df.to_excel(writer, index=False, sheet_name='IEC_Analysis_Results')
      output.seek(0)
      return output.getvalue()


    # PDF Generator Function taking explicit target_df and explicit date constraints
    def generate_pdf_report(target_df, m_id, s_date, e_date):
      d_sel, d_id, m_no, cap, l_series, c_col, t_data = analyze_dt(
          target_df, m_id
      )

      fig_pdf, ax_pdf = plt.subplots(figsize=(10, 4.2), dpi=200)
      if not d_sel.empty:
        ax_pdf.plot(
            d_sel[time_col],
            d_sel[c_col],
            color='#1f77b4',
            linewidth=1.0,
            label='Avg Loading',
        )
        avg_l_val = l_series.mean()
        ax_pdf.axhline(
            y=avg_l_val,
            color='red',
            linestyle='--',
            linewidth=1.2,
            label='80% Loading',
        )
        ax_pdf.set_xlim(pd.to_datetime(s_date), pd.to_datetime(e_date) + pd.Timedelta(days=1))

      ax_pdf.set_title(
          'DT Loading Status as per IEC OL Criteria (Filtered Range)',
          fontsize=10,
          fontweight='bold',
          pad=10,
      )
      ax_pdf.set_xlabel('Timestamp', fontsize=9, fontweight='bold')
      ax_pdf.set_ylabel('Current (Amperes)', fontsize=9, fontweight='bold')
      ax_pdf.grid(True, linestyle='--', alpha=0.5)
      ax_pdf.legend(loc='upper left', fontsize=8)

      plt.subplots_adjust(top=0.90, bottom=0.15, left=0.08, right=0.95)

      img_buf = io.BytesIO()
      plt.savefig(img_buf, format='png', bbox_inches='tight')
      plt.close(fig_pdf)
      img_buf.seek(0)

      pdf_buf = io.BytesIO()
      doc = SimpleDocTemplate(
          pdf_buf,
          pagesize=landscape(letter),
          rightMargin=30,
          leftMargin=30,
          topMargin=30,
          bottomMargin=30,
      )
      story = []

      styles = getSampleStyleSheet()
      title_style = ParagraphStyle(
          'ReportTitle',
          parent=styles['Heading1'],
          fontSize=15,
          textColor=colors.HexColor('#1f77b4'),
          spaceAfter=6,
          alignment=1,
      )

      meta_style = ParagraphStyle(
          'ReportMeta',
          parent=styles['Normal'],
          fontSize=10,
          alignment=1,
          spaceAfter=12,
      )

      story.append(
          Paragraph(
              'Distribution Transformer Overloading Report', title_style
          )
      )
      story.append(
          Paragraph(
              f'<b>Meter No:</b> {m_no} &nbsp;&nbsp;|&nbsp;&nbsp; <b>DT'
              f' ID:</b> {d_id} &nbsp;&nbsp;|&nbsp;&nbsp; <b>Capacity:</b>'
              f' {cap} kVA <br/><b>Time Slot:</b> {s_date} to {e_date}',
              meta_style,
          )
      )

      story.append(Image(img_buf, width=680, height=285))
      story.append(Spacer(1, 10))

      table_content = [
          [
              'Loading Criteria',
              'Violation Instances',
              'Permissible Duration (min)',
          ]
      ]
      for row in t_data:
        table_content.append([str(row[0]), str(row[1]), str(row[2])])

      t_style_commands = [
          ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f77b4')),
          ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
          ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
          ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
          ('FONTSIZE', (0, 0), (-1, 0), 9),
          ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
          ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d0d0d0')),
          ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
          ('FONTSIZE', (0, 1), (-1, -1), 8),
          ('TOPPADDING', (0, 1), (-1, -1), 4),
          ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
      ]

      for idx, row in enumerate(t_data):
        instances = row[1]
        row_idx = idx + 1
        if instances > 0:
          t_style_commands.append(
              ('BACKGROUND', (0, row_idx), (-1, row_idx), colors.HexColor('#fdf2f2'))
          )
          t_style_commands.append(
              ('TEXTCOLOR', (0, row_idx), (-1, row_idx), colors.HexColor('#8B0000'))
          )
          t_style_commands.append(
              ('FONTNAME', (0, row_idx), (-1, row_idx), 'Helvetica-Bold')
          )
        else:
          t_style_commands.append(
              ('BACKGROUND', (0, row_idx), (-1, row_idx), colors.HexColor('#f9f9f9'))
          )
          t_style_commands.append(
              ('TEXTCOLOR', (0, row_idx), (-1, row_idx), colors.HexColor('#333333'))
          )

      summary_table = Table(
          table_content, colWidths=[220, 220, 240], style=TableStyle(t_style_commands)
      )
      story.append(summary_table)

      doc.build(story)
      pdf_buf.seek(0)
      return pdf_buf


    # --- DASHBOARD ACTION BUTTONS ---
    st.markdown('### 📥 Export Reports & Analysis')
    col_b1, col_b2, col_b3 = st.columns(3)

    with col_b1:
      single_pdf = generate_pdf_report(df_current, selected_meter, start_date, end_date)
      st.download_button(
          label='📄 Download Current DT PDF',
          data=single_pdf,
          file_name=f'DT_Report_Meter_{selected_meter}_{start_date}_to_{end_date}.pdf',
          mime='application/pdf',
          use_container_width=True,
      )

    with col_b2:
      if st.button('⚙️ Generate All DTs PDF Report', use_container_width=True):
        with st.spinner('Generating batch PDF report restricted to selected date range...'):
          batch_pdf_buf = io.BytesIO()
          doc_batch = SimpleDocTemplate(
              batch_pdf_buf,
              pagesize=landscape(letter),
              rightMargin=30,
              leftMargin=30,
              topMargin=30,
              bottomMargin=30,
          )
          story_batch = []

          styles = getSampleStyleSheet()
          title_style = ParagraphStyle(
              'ReportTitle',
              parent=styles['Heading1'],
              fontSize=15,
              textColor=colors.HexColor('#1f77b4'),
              spaceAfter=6,
              alignment=1,
          )
          meta_style = ParagraphStyle(
              'ReportMeta',
              parent=styles['Normal'],
              fontSize=10,
              alignment=1,
              spaceAfter=12,
          )

          for idx, m in enumerate(unique_meters):
            d_sub_all = df[df[meter_col] == m].sort_values(time_col)
            mask_batch = (d_sub_all[time_col].dt.date >= start_date) & (
                d_sub_all[time_col].dt.date <= end_date
            )
            d_sub = d_sub_all.loc[mask_batch]

            if len(d_sub) == 0:
              continue

            d_sel, d_id, m_no, cap, l_series, c_col, t_data = analyze_dt(
                d_sub, m
            )

            fig_b, ax_b = plt.subplots(figsize=(10, 4.2), dpi=200)
            ax_b.plot(
                d_sel[time_col],
                d_sel[c_col],
                color='#1f77b4',
                linewidth=1.0,
                label='Avg Loading',
            )
            avg_l_val = l_series.mean()
            ax_b.axhline(
                y=avg_l_val,
                color='red',
                linestyle='--',
                linewidth=1.2,
                label='80% Loading',
            )
            ax_b.set_xlim(pd.to_datetime(start_date), pd.to_datetime(end_date) + pd.Timedelta(days=1))

            ax_b.set_title(
                'DT Loading Status as per IEC OL Criteria (Filtered Range)',
                fontsize=10,
                fontweight='bold',
                pad=10,
            )
            ax_b.set_xlabel('Timestamp', fontsize=9, fontweight='bold')
            ax_b.set_ylabel('Current (Amperes)', fontsize=9, fontweight='bold')
            ax_b.grid(True, linestyle='--', alpha=0.5)
            ax_b.legend(loc='upper left', fontsize=8)

            plt.subplots_adjust(top=0.90, bottom=0.15, left=0.08, right=0.95)

            img_buf = io.BytesIO()
            plt.savefig(img_buf, format='png', bbox_inches='tight')
            plt.close(fig_b)
            img_buf.seek(0)

            story_batch.append(
                Paragraph(
                    f'Distribution Transformer Overloading Report ({idx + 1} of'
                    f' {len(unique_meters)})',
                    title_style,
                )
            )
            story_batch.append(
                Paragraph(
                    f'<b>Meter No:</b> {m_no} &nbsp;&nbsp;|&nbsp;&nbsp; <b>DT'
                    f' ID:</b> {d_id} &nbsp;&nbsp;|&nbsp;&nbsp; <b>Capacity:</b>'
                    f' {cap} kVA <br/><b>Time Slot:</b> {start_date} to {end_date}',
                    meta_style,
                )
            )
            story_batch.append(Image(img_buf, width=680, height=285))
            story_batch.append(Spacer(1, 10))

            table_content = [
                [
                    'Loading Criteria',
                    'Violation Instances',
                    'Permissible Duration (min)',
                ]
            ]
            for row in t_data:
              table_content.append([str(row[0]), str(row[1]), str(row[2])])

            t_style_commands = [
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f77b4')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d0d0d0')),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
                ('TOPPADDING', (0, 1), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
            ]

            for i_idx, row in enumerate(t_data):
              instances = row[1]
              r_idx = i_idx + 1
              if instances > 0:
                t_style_commands.append(
                    ('BACKGROUND', (0, r_idx), (-1, r_idx), colors.HexColor('#fdf2f2'))
                )
                t_style_commands.append(
                    ('TEXTCOLOR', (0, r_idx), (-1, r_idx), colors.HexColor('#8B0000'))
                )
                t_style_commands.append(
                    ('FONTNAME', (0, r_idx), (-1, r_idx), 'Helvetica-Bold')
                )
              else:
                t_style_commands.append(
                    ('BACKGROUND', (0, r_idx), (-1, r_idx), colors.HexColor('#f9f9f9'))
                )
                t_style_commands.append(
                    ('TEXTCOLOR', (0, r_idx), (-1, r_idx), colors.HexColor('#333333'))
                )

            summary_table = Table(
                table_content, colWidths=[220, 220, 240], style=TableStyle(t_style_commands)
            )
            story_batch.append(summary_table)

            if idx < len(unique_meters) - 1:
              story_batch.append(PageBreak())

          doc_batch.build(story_batch)
          batch_pdf_buf.seek(0)
          st.session_state['batch_pdf_data'] = batch_pdf_buf.getvalue()
          st.success('Batch PDF generated successfully!')

      if 'batch_pdf_data' in st.session_state:
        st.download_button(
            label='📥 Download All DTs PDF Report',
            data=st.session_state['batch_pdf_data'],
            file_name=f'All_DTs_Report_{start_date}_to_{end_date}.pdf',
            mime='application/pdf',
            use_container_width=True,
        )

    with col_b3:
      st.markdown('### 📊 Analysis Results')
      excel_data = generate_excel_analysis_report()
      st.download_button(
          label='📥 Download Analysis Excel',
          data=excel_data,
          file_name=f'IEC_Analysis_Results_{start_date}_to_{end_date}.xlsx',
          mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
          use_container_width=True,
      )
else:
  st.info('👆 Please upload your master CSV file using the file uploader above.')
