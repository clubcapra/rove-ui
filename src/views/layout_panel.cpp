#include "views/layout_panel.h"
#include <QDebug>

LayoutPanel::LayoutPanel(QWidget *parent)
    : QWidget(parent)
    , layout_type_("grid")
    , rows_(1)
    , columns_(1)
    , grid_layout_(nullptr)
    , horizontal_layout_(nullptr)
    , vertical_layout_(nullptr)
    , splitter_(nullptr)
{
}

LayoutPanel::~LayoutPanel()
{
    clearLayout();
}

void LayoutPanel::configureLayout(const ConfigManager::PanelConfig& config)
{
    layout_type_ = config.layout_type;
    rows_ = config.rows;
    columns_ = config.columns;
    
    clearLayout();
    
    if (layout_type_ == "grid") {
        setupGridLayout(rows_, columns_);
    } else if (layout_type_ == "horizontal") {
        setupHorizontalLayout();
    } else if (layout_type_ == "vertical") {
        setupVerticalLayout();
    } else {
        // Default to grid
        setupGridLayout(rows_, columns_);
    }
}

void LayoutPanel::setupGridLayout(int rows, int cols)
{
    grid_layout_ = new QGridLayout(this);
    grid_layout_->setSpacing(5);
    grid_layout_->setContentsMargins(5, 5, 5, 5);
    setLayout(grid_layout_);
    
    qDebug() << "LayoutPanel: Grille configurée avec" << rows << "lignes et" << cols << "colonnes";
}

void LayoutPanel::setupHorizontalLayout()
{
    splitter_ = new QSplitter(Qt::Horizontal, this);
    
    QVBoxLayout* layout = new QVBoxLayout(this);
    layout->setContentsMargins(0, 0, 0, 0);
    layout->addWidget(splitter_);
    setLayout(layout);
    
    qDebug() << "LayoutPanel: Layout horizontal configuré";
}

void LayoutPanel::setupVerticalLayout()
{
    splitter_ = new QSplitter(Qt::Vertical, this);
    
    QVBoxLayout* layout = new QVBoxLayout(this);
    layout->setContentsMargins(0, 0, 0, 0);
    layout->addWidget(splitter_);
    setLayout(layout);
    
    qDebug() << "LayoutPanel: Layout vertical configuré";
}

void LayoutPanel::addWidget(QWidget* widget, int row, int col)
{
    if (!widget) return;
    
    child_widgets_.append(widget);
    
    if (grid_layout_) {
        grid_layout_->addWidget(widget, row, col);
        qDebug() << "LayoutPanel: Widget ajouté à la position [" << row << "," << col << "]";
    } else if (splitter_) {
        splitter_->addWidget(widget);
        qDebug() << "LayoutPanel: Widget ajouté au splitter";
    }
}

void LayoutPanel::addWidget(QWidget* widget)
{
    if (!widget) return;
    
    child_widgets_.append(widget);
    
    if (splitter_) {
        splitter_->addWidget(widget);
        qDebug() << "LayoutPanel: Widget ajouté au splitter";
    } else if (grid_layout_) {
        // Ajouter à la prochaine position disponible
        int count = child_widgets_.size() - 1;
        int row = count / columns_;
        int col = count % columns_;
        grid_layout_->addWidget(widget, row, col);
        qDebug() << "LayoutPanel: Widget ajouté automatiquement à [" << row << "," << col << "]";
    }
}

void LayoutPanel::clearLayout()
{
    // Nettoyer les widgets enfants
    for (QWidget* widget : child_widgets_) {
        if (widget) {
            widget->setParent(nullptr);
        }
    }
    child_widgets_.clear();
    
    // Nettoyer les layouts
    if (layout()) {
        QLayoutItem* item;
        while ((item = layout()->takeAt(0)) != nullptr) {
            delete item->widget();
            delete item;
        }
        delete layout();
    }
    
    grid_layout_ = nullptr;
    horizontal_layout_ = nullptr;
    vertical_layout_ = nullptr;
    
    if (splitter_) {
        splitter_->deleteLater();
        splitter_ = nullptr;
    }
}
