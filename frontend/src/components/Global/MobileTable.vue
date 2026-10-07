/**
 * 通用移动端表格→卡片列表转换器
 *
 * 设计依据（行业标准）：
 * - mdn / impeccable adapt.md：移动端表格应转为卡片（display:block + data-label）
 * - Material Design：触控目标 ≥48dp；Apple HIG：≥44pt
 * - 单列卡片 + 字段标签前缀，保持信息架构与桌面一致
 *
 * 用法：在页面 el-table 旁并列一个 MobileTable 组件，CSS 控制各自显隐：
 *   el-table 加 class="hidden-sm-and-down"，MobileTable 加 class="hidden-md-and-up"
 * columns: [{ prop, label, skip?, slot?, formatter? }]
 * 具名列通过 #动态slot 自定义渲染（slot 名 = 列 slot 字段）。
 */
<template>
  <div class="mobile-table">
    <div
      v-for="(row, i) in rows"
      :key="rowKey ? String(row[rowKey]) : i"
      class="mt-card"
      :class="{ clickable: !!clickable, selected: selectable && isSelected(row) }"
      @click="clickable && emit('row-click', row)"
    >
      <!-- 卡片头：主字段（第一列）+ 可选右侧字段（副列） -->
      <div class="mt-card-head">
        <div class="mt-title">
          <slot v-if="$slots.head" name="head" :row="row" :index="i" />
          <template v-else>{{ display(row, headColumn) }}</template>
        </div>
        <div v-if="headRightColumn" class="mt-head-right">
          <slot v-if="$slots.headRight" name="headRight" :row="row" :index="i" />
          <template v-else>{{ display(row, headRightColumn) }}</template>
        </div>
      </div>

      <!-- 字段区：其余列以 label: value 呈现 -->
      <div class="mt-fields">
        <div v-for="col in fieldColumns" :key="col.prop" class="mt-field">
          <span class="mt-label">{{ col.label }}</span>
          <span class="mt-value">
            <slot v-if="col.slot && $slots[col.slot]" :name="col.slot" :row="row" :index="i" />
            <template v-else>{{ display(row, col) }}</template>
          </span>
        </div>
      </div>

      <!-- 操作区：具名操作按钮 -->
      <div v-if="$slots.actions" class="mt-actions" @click.stop>
        <slot name="actions" :row="row" :index="i" />
      </div>
    </div>
    <el-empty v-if="!rows?.length" description="暂无数据" :image-size="72" />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

export interface MobileColumn {
  /** 字段名 */
  prop: string
  /** 列标题（卡片里作为字段标签） */
  label: string
  /** 自定义渲染 slot 名；提供时卡片用同名作用域插槽 */
  slot?: string
  /** 文本格式化 */
  formatter?: (row: any, column: MobileColumn) => string
  /** 该列不进卡片字段区（仅用于 head/headRight 已消费等场景） */
  skip?: boolean
}

/**
 * 行类型故意放开为 any 兼容层：
 * 调用方持有具体业务类型（AnalysisTask / FavoriteItem / StockInfo），
 * 若强类型 Record<string, unknown> 会迫使所有插槽回调做不安全转换，
 * 得不偿失。组件内部只做只读展示，不做写操作。
 */
const props = withDefaults(
  defineProps<{
    /** 数据行 */
    rows: any[]
    /** 列定义（与桌面 el-table 列对应） */
    columns: MobileColumn[]
    /** 行唯一键字段 */
    rowKey?: string
    /** 作为卡片标题的列（默认第一列） */
    headProp?: string
    /** 标题右侧的强调列（如涨跌幅） */
    headRightProp?: string
    /** 卡片可点击 */
    clickable?: boolean
    /** 可选中（多选） */
    selectable?: boolean
  }>(),
  {
    rowKey: '',
    headProp: '',
    headRightProp: '',
    clickable: false,
    selectable: false
  }
)

const emit = defineEmits<{
  'row-click': [row: any]
}>()

const selection = defineModel<any[]>('selection', { default: () => [] })

const headColumn = computed(() => {
  if (props.headProp) {
    return props.columns.find((c) => c.prop === props.headProp) ?? props.columns[0]
  }
  return props.columns[0]
})

const headRightColumn = computed(() => {
  if (!props.headRightProp) return null
  return props.columns.find((c) => c.prop === props.headRightProp) ?? null
})

const fieldColumns = computed(() =>
  props.columns.filter(
    (c) =>
      !c.skip &&
      c.prop !== headColumn.value?.prop &&
      c.prop !== headRightColumn.value?.prop
  )
)

function display(row: any, col?: MobileColumn): string {
  if (!col) return ''
  if (col.formatter) return col.formatter(row, col)
  const v = row?.[col.prop]
  if (v === null || v === undefined || v === '') return '-'
  return String(v)
}

function isSelected(row: any): boolean {
  if (!props.rowKey) return false
  return selection.value.some((r) => r?.[props.rowKey] === row?.[props.rowKey])
}
</script>

<style lang="scss" scoped>
.mobile-table {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.mt-card {
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 10px;
  padding: 12px 14px;

  &.clickable {
    cursor: pointer;
  }

  &.clickable:active {
    background: var(--el-fill-color-light);
  }

  &.selected {
    border-color: var(--el-color-primary);
    background: var(--el-color-primary-light-9);
  }
}

.mt-card-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}

.mt-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mt-head-right {
  font-size: 14px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  flex-shrink: 0;
}

.mt-fields {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 6px 14px;
}

.mt-field {
  display: flex;
  align-items: baseline;
  gap: 6px;
  min-width: 0;
}

.mt-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  flex-shrink: 0;
}

.mt-value {
  font-size: 13px;
  color: var(--el-text-color-primary);
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}

.mt-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px dashed var(--el-border-color-lighter);

  :deep(.el-button) {
    margin-left: 0;
    min-height: 36px;
  }
}

/* 极窄屏（≤360px）：字段区退化为单列 */
@media (max-width: 360px) {
  .mt-fields {
    grid-template-columns: 1fr;
  }
}
</style>
