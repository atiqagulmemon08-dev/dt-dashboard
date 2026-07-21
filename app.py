import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title='DT Overloading Dashboard', page_icon='⚡', layout='wide'
)

st.title('⚡ Distribution Transformer (DT) Overloading Dashboard')
st.markdown(
    'Upload your master dataset containing multiple DTs to analyze IEC'
    ' overloading criteria and visualize graphs interactively.'
)

uploaded_file = st.file_uploader(
    'Upload Master CSV File (Multi-DT Data)', type=['csv']
)

if uploaded_file is not None:

  @st.cache_data
  def load_data(file):
    return pd.read_csv(file)

  df = load_data(uploaded_file)

  if 'Date + Time' in df.columns:
    df['Date + Time'] = pd.to_datetime(df['Date + Time'])

  meter_col = (
      'Meter No'
      if 'Meter No' in df.columns
      else ('Meter_No' if 'Meter_No' in df.columns else None)
  )
  dt_col = (
      'DTS (kVA)'
      if 'DTS (kVA)' in df.columns
      else ('DT ID' if 'DT ID' in df.columns else meter_col)
  )

  if meter_col is None:
    st.error("Could not find a 'Meter No' or 'Meter_No' column in your dataset.")
  else:
    st.sidebar.header('Selection Filter')
    unique_meters = df[meter_col].dropna().unique()
    selected_meter = st.sidebar.selectbox(
        'Select Meter No / DT ID:', unique_meters
    )

    df_selected = df[df[meter_col] == selected_meter].sort_values(
        'Date + Time'
    )

    dt_id = (
        str(df_selected[dt_col].iloc[0])
        if dt_col in df_selected.columns
        else 'N/A'
    )
    meter_no = str(selected_meter)
    capacity = (
        str(df_selected['DTS (kVA)'].iloc[0])
        if 'DTS (kVA)' in df_selected.columns
        else 'N/A'
    )

    if 'Limit(80% of LT Amps Rated)' in df_selected.columns:
      limit_series = df_selected['Limit(80% of LT Amps Rated)']
    else:
      limit_series = df_selected['LT Amps rated'] * 0.80

    df_selected['Loading_Pct'] = (
        df_selected['Avg Current'] / df_selected['LT Amps rated']
    ) * 100

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
          df_selected['Loading_Pct'], params['threshold'], params['min_rows']
      )
      table_data.append([label, instances, params['perm_dur']])

    total_violations = sum([row[1] for row in table_data])
    col1, col2, col3 = st.columns(3)
    col1.metric('Selected Meter No', meter_no)
    col2.metric('DT Capacity', f'{capacity} kVA')
    col3.metric('Total Overloading Instances', total_violations)

    st.markdown('---')

    fig, ax = plt.subplots(figsize=(14, 7), dpi=300)
    ax.plot(
        df_selected['Date + Time'],
        df_selected['Avg Current'],
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
        df_selected['Date + Time'].iloc[int(len(df_selected) * 0.70)],
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
else:
  st.info(
      '👆 Please upload your master CSV file using the file uploader above to'
      ' begin.'
  )
