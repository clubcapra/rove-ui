#ifndef LAYOUT_PANEL_H
#define LAYOUT_PANEL_H

#include <QWidget>
#include <QGridLayout>
#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QSplitter>
#include "core/config_manager.h"

class LayoutPanel : public QWidget
{
    Q_OBJECT

public:
    explicit LayoutPanel(QWidget *parent = nullptr);
    ~LayoutPanel();

    // Configure le layout à partir de la configuration
    void configureLayout(const ConfigManager::PanelConfig& config);
    
    // Ajoute un widget dans le layout
    void addWidget(QWidget* widget, int row, int col);
    void addWidget(QWidget* widget); // Pour layouts simples
    
    // Getters
    int getRows() const { return rows_; }
    int getColumns() const { return columns_; }
    QString getLayoutType() const { return layout_type_; }

private:
    void setupGridLayout(int rows, int cols);
    void setupHorizontalLayout();
    void setupVerticalLayout();
    void clearLayout();
    
    QString layout_type_;  // "grid", "horizontal", "vertical"
    int rows_;
    int columns_;
    
    QGridLayout* grid_layout_;
    QHBoxLayout* horizontal_layout_;
    QVBoxLayout* vertical_layout_;
    QSplitter* splitter_;  // Pour layouts redimensionnables
    
    QList<QWidget*> child_widgets_;
};

#endif // LAYOUT_PANEL_H
