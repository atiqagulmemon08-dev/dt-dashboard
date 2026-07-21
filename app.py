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
    ' overloading criteria, visualize graphs interactively, and export'
    ' professional PDF reports.'
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
    df[time_col] = pd.to_datetime(df[time_col])
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
    st.error(
        'Could not find a timestamp or date column in your dataset. Please'
        ' ensure your CSV has a date/time column.'
    )
  else:
    st.sidebar.header('Selection Filter')
    unique_meters = df[meter_col].dropna().unique()
    selected_meter = st.sidebar.selectbox(
        'Select Meter No / DT ID:', unique_meters
    )

    # Helper function to compute analysis for any given meter dataframe subset
    def analyze_dt(df_selected, m_id):
      dt_id = str(m_id)
      meter_no = str(m_id)
      capacity = (
          str(df_selected['DTS (kVA)'].iloc[0])
          if 'DTS (kVA)' in df_selected.columns
          else (
              'Capacity' in df_selected.columns
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

      if limit_col and limit_col in df_selected.columns:
        limit_series = df_selected[limit_col]
      elif lt_amps_col:
        limit_series = df_selected[lt_amps_col] * 0.80
      else:
        limit_series = df_selected['Avg Current'] * 0.80

      current_col = next(
          (
              col
              for col in ['Avg Current', 'Current', 'Avg_Current']
              if col in df.columns
          ),
          df.columns[1],
      )

      if lt_amps_col:
        df_selected['Loading_Pct'] = (
            df_selected[current_col] / df_selected[lt_amps_col]
        ) * 100
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

    # Filter for current view
    df_current = df[df[meter_col] == selected_meter].sort_values(time_col)
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
    col3.metric('Total Overloading Instances', total_violations)

    st.markdown('---')

    # Generate interactive plot
    fig, ax = plt.subplots(figsize=(14, 7), dpi=300)
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

    ax.text(
        df_selected[time_col].iloc[int(len(df_selected) * 0.70)],
        avg_limit_value + 15,
        '80% Loading',
        color='red',
        fontsize=9,
        fontweight='bold',
    )

    title_str = (
        f'DT ID: {dt_id}  |  Meter No: {meter_no}  |  Capacity: {capacity}'
    )
    fig.suptitle(title_str, fontsize=11, fontweight='bold', y=0.96)
    ax.set_title(
        'DT Loading Status as per IEC OL Criteria',
        fontsize=10,
        fontweight='bold',
        pad=15,
    )

    ax.set_xlabel('Timestamp', fontsize=10, fontweight='bold')
    ax.set_ylabel('Current (Amperes)', fontsize=10, fontweight='bold')

    ax.grid(True, linestyle='--', alpha=0.5)
    ax.legend(loc='upper left')

    col_labels = ['Loading', 'Instances', 'Perm. Dur. (min)']
    table_cell_text = [[row[0], str(row[1]), str(row[2])] for row in table_data]

    table = ax.table(
        cellText=table_cell_text,
        colLabels=col_labels,
        loc='upper right',
        bbox=[0.78, 1.01, 0.22, 0.28],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(8)

    for key, cell in table.get_celld().items():
      row_idx = key[0]
      cell.set_edgecolor('#b0b0b0')
      if row_idx == 0:
        cell.set_facecolor('#1f77b4')
        cell.set_text_props(color='white', fontweight='bold')
      else:
        instance_count = table_data[row_idx - 1][1]
        if instance_count > 0:
          cell.set_facecolor('#fdf2f2')
          cell.set_text_props(color='darkred', fontweight='bold')
        else:
          cell.set_facecolor('#ffffff')
          cell.set_text_props(color='#333333', fontweight='normal')

    plt.subplots_adjust(top=0.85, bottom=0.1, left=0.08, right=0.95)
    st.pyplot(fig)

    with st.expander('View Raw Data Records for Selected DT'):
      st.dataframe(df_selected)

    st.markdown('---')


    # PDF Generator Function for a single DT report
    def generate_pdf_report(target_df, m_id):
      d_sel, d_id, m_no, cap, l_series, c_col, t_data = analyze_dt(
          target_df, m_id
      )

      fig_pdf, ax_pdf = plt.subplots(figsize=(10, 5), dpi=200)
      ax_pdf.plot(
          d_sel[time_col],
          d_sel[c_col],
          color='#1f77b4',
          linewidth=0.8,
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

      t_str = f'DT ID: {d_id}  |  Meter No: {m_no}  |  Capacity: {cap}'
      fig_pdf.suptitle(t_str, fontsize=10, fontweight='bold', y=0.96)
      ax_pdf.set_title(
          'DT Loading Status as per IEC OL Criteria',
          fontsize=9,
          fontweight='bold',
          pad=12,
      )
      ax_pdf.set_xlabel('Timestamp', fontsize=8, fontweight='bold')
      ax_pdf.set_ylabel('Current (Amperes)', fontsize=8, fontweight='bold')
      ax_pdf.grid(True, linestyle='--', alpha=0.5)
      ax_pdf.legend(loc='upper left', fontsize=8)

      col_lbls = [
          'Loading Criteria',
          'Violation Instances',
          'Permissible Duration (min)',
      ]
      t_txt = [[row[0], str(row[1]), str(row[2])] for row in t_data]

      tbl = ax_pdf.table(
          cellText=t_txt,
          colLabels=col_lbls,
          loc='upper right',
          bbox=[0.72, 1.01, 0.28, 0.28],
      )
      tbl.auto_set_font_size(False)
      tbl.set_fontsize(7)

      for key, cell in tbl.get_celld().items():
        row_idx = key[0]
        cell.set_edgecolor('#b0b0b0')
        if row_idx == 0:
          cell.set_facecolor('#1f77b4')
          cell.set_text_props(color='white', fontweight='bold')
        else:
          inst_cnt = t_data[row_idx - 1][1]
          if inst_cnt > 0:
            cell.set_facecolor('#fdf2f2')
            cell.set_text_props(color='darkred', fontweight='bold')
          else:
            cell.set_facecolor('#ffffff')
            cell.set_text_props(color='#333333', fontweight='normal')

      plt.subplots_adjust(top=0.82, bottom=0.12, left=0.08, right=0.92)

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
          fontSize=16,
          textColor=colors.HexColor('#1f77b4'),
          spaceAfter=10,
          alignment=1,
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
              f' {cap} kVA',
              styles['Normal'],
          )
      )
      story.append(Spacer(1, 15))
      story.append(Image(img_buf, width=700, height=330))
      story.append(Spacer(1, 10))

      doc.build(story)
      pdf_buf.seek(0)
      return pdf_buf


    # Two Download Buttons in Columns
    col_b1, col_b2 = st.columns(2)

    with col_b1:
      st.markdown('### 📄 Current DT Report')
      single_pdf = generate_pdf_report(df_current, selected_meter)
      st.download_button(
          label='📥 Download Current DT Graph PDF',
          data=single_pdf,
          file_name=f'DT_Report_Meter_{selected_meter}.pdf',
          mime='application/pdf',
          use_container_width=True,
      )

    with col_b2:
      st.markdown('### 📚 Batch Report (All DTs)')
      if st.button('⚙️ Generate All DTs PDF Report', use_container_width=True):
        with st.spinner(
            'Generating batch PDF report for all DTs in the dataset... This may'
            ' take a moment.'
        ):
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
              fontSize=16,
              textColor=colors.HexColor('#1f77b4'),
              spaceAfter=10,
              alignment=1,
          )

          for idx, m in enumerate(unique_meters):
            d_sub = df[df[meter_col] == m].sort_values(time_col)
            if len(d_sub) == 0:
              continue

            d_sel, d_id, m_no, cap, l_series, c_col, t_data = analyze_dt(
                d_sub, m
            )

            fig_b, ax_b = plt.subplots(figsize=(10, 4.5), dpi=200)
            ax_b.plot(
                d_sel[time_col],
                d_sel[c_col],
                color='#1f77b4',
                linewidth=0.8,
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

            t_str = f'DT ID: {d_id}  |  Meter No: {m_no}  |  Capacity: {cap}'
            fig_b.suptitle(t_str, fontsize=10, fontweight='bold', y=0.96)
            ax_b.set_title(
                'DT Loading Status as per IEC OL Criteria',
                fontsize=9,
                fontweight='bold',
                pad=12,
            )
            ax_b.set_xlabel('Timestamp', fontsize=8, fontweight='bold')
            ax_b.set_ylabel('Current (Amperes)', fontsize=8, fontweight='bold')
            ax_b.grid(True, linestyle='--', alpha=0.5)
            ax_b.legend(loc='upper left', fontsize=8)

            col_lbls = [
                'Loading Criteria',
                'Violation Instances',
                'Permissible Duration (min)',
            ]
            t_txt = [[row[0], str(row[1]), str(row[2])] for row in t_data]

            tbl = ax_b.table(
                cellText=t_txt,
                colLabels=col_lbls,
                loc='upper right',
                bbox=[0.72, 1.01, 0.28, 0.28],
            )
            tbl.auto_set_font_size(False)
            tbl.set_fontsize(7)

            for key, cell in tbl.get_celld().items():
              row_idx = key[0]
              cell.set_edgecolor('#b0b0b0')
              if row_idx == 0:
                cell.set_facecolor('#1f77b4')
                cell.set_text_props(color='white', fontweight='bold')
              else:
                inst_cnt = t_data[row_idx - 1][1]
                if inst_cnt > 0:
                  cell.set_facecolor('#fdf2f2')
                  cell.set_text_props(color='darkred', fontweight='bold')
                else:
                  cell.set_facecolor('#ffffff')
                  cell.set_text_props(color='#333333', fontweight='normal')

            plt.subplots_adjust(top=0.82, bottom=0.12, left=0.08, right=0.92)

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
                    f' {cap} kVA',
                    styles['Normal'],
                )
            )
            story_batch.append(Spacer(1, 10))
            story_batch.append(Image(img_buf, width=700, height=310))

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
            file_name='All_DTs_Comprehensive_Report.pdf',
            mime='application/pdf',
            use_container_width=True,
        )
else:
  st.info(
      '👆 Please upload your master CSV file using the file uploader above to'
      ' begin.'
  )
